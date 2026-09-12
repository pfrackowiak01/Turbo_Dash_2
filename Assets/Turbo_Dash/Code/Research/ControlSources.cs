using System;
using UnityEngine;

namespace TurboDash.Research
{
    public enum DiscreteAction { Left = 0, None = 1, Right = 2 }
    public enum ActionSpaceType { Discrete, Continuous }

    public readonly struct SteeringAction
    {
        // Positive means LEFT from the player's perspective in both locations.
        public readonly float Value;
        public SteeringAction(float value)
        {
            if (float.IsNaN(value) || float.IsInfinity(value)) throw new ArgumentOutOfRangeException(nameof(value));
            Value = Mathf.Clamp(value, -1f, 1f);
        }
        public static SteeringAction FromDiscrete(DiscreteAction action)
        {
            switch (action)
            {
                case DiscreteAction.Left: return new SteeringAction(1);
                case DiscreteAction.None: return new SteeringAction(0);
                case DiscreteAction.Right: return new SteeringAction(-1);
                default: throw new ArgumentOutOfRangeException(nameof(action));
            }
        }
    }

    public interface IResearchController
    {
        string ControllerType { get; }
        ActionSpaceType ActionSpaceType { get; }
        void ResetEpisode(int seed);
        SteeringAction Decide(ObservationFrame observation);
    }

    // Diagnostic controller. This is deliberately not labelled a rule-based baseline.
    public sealed class NoActionController : IResearchController
    {
        public string ControllerType => "NoAction";
        public ActionSpaceType ActionSpaceType => ActionSpaceType.Discrete;
        public void ResetEpisode(int seed) { }
        public SteeringAction Decide(ObservationFrame observation) => SteeringAction.FromDiscrete(DiscreteAction.None);
    }

    // An algorithm may instead implement IResearchController directly. No ML dependency.
    public sealed class SubmittedActionController : IResearchController
    {
        public string ControllerType { get; }
        public ActionSpaceType ActionSpaceType { get; }
        private SteeringAction current;
        public SubmittedActionController(string controllerType, ActionSpaceType actionSpaceType)
        {
            if (string.IsNullOrWhiteSpace(controllerType)) throw new ArgumentException("Controller name is required.");
            ControllerType = controllerType;
            ActionSpaceType = actionSpaceType;
        }
        public void Submit(DiscreteAction action)
        {
            if (ActionSpaceType != ActionSpaceType.Discrete) throw new InvalidOperationException("Continuous controller.");
            current = SteeringAction.FromDiscrete(action);
        }
        public void Submit(float steering)
        {
            if (ActionSpaceType != ActionSpaceType.Continuous) throw new InvalidOperationException("Discrete controller.");
            current = new SteeringAction(steering);
        }
        public void ResetEpisode(int seed) { current = new SteeringAction(0); }
        public SteeringAction Decide(ObservationFrame observation) => current;
    }

    // Legacy human input returns angular speed: preserves both manual 144 deg/s
    // and the original gyro limit 264 deg/s at the scene's 12 / 22 settings.
    public sealed class HumanController
    {
        private readonly float screenWidth = Screen.width;
        public float ReadDegreesPerSecond(EnvironmentMovement environment)
        {
            int mode = SaveAndLoadManager.Instance.usedGameMode.Index;
            if (mode == 1)
            {
                bool left = Input.GetKey(KeyCode.LeftArrow), right = Input.GetKey(KeyCode.RightArrow);
                if (Input.GetMouseButtonDown(0) || Input.GetMouseButtonDown(1) || Input.touchCount > 0)
                    foreach (Touch touch in Input.touches)
                        if (touch.position.x < screenWidth / 2) left = true; else right = true;
                return ManualDegreesPerSecond(left, right, environment.rotationSpeed);
            }
            if (mode == 0)
            {
                Quaternion rotation = Quaternion.Inverse(GameManager.Instance.initialRotation) * Input.gyro.attitude;
                return Mathf.Clamp(rotation.z * Mathf.Rad2Deg, -environment.maxRotationSpeed,
                    environment.maxRotationSpeed) * environment.rotationSpeed;
            }
            return 0;
        }
        public static float ManualDegreesPerSecond(bool left, bool right, float speed)
            => left == right ? 0 : (left ? 1 : -1) * speed * speed;
    }
}
