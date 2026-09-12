using TurboDash.Research;
using UnityEngine;

[DefaultExecutionOrder(-9000)]
public class EnvironmentMovement : MonoBehaviour
{
    // Existing serialized fields retain their names and values.
    public float rotationSpeed = 12f;
    public float maxRotationSpeed = 22f;
    public float ResearchDegreesPerSecond => rotationSpeed * rotationSpeed;
    private HumanController human;

    private void Start() { human = new HumanController(); }
    private void Update()
    {
        if (!ResearchMode.Active) ApplyDegreesPerSecond(human.ReadDegreesPerSecond(this), Time.deltaTime);
    }
    private void FixedUpdate()
    {
        if (ResearchMode.Running)
        {
            try
            {
                var mode = ResearchMode.Instance;
                Physics.SyncTransforms();
                var action = mode.Controller.Decide(mode.Observations.Capture());
                if (mode.Controller.ActionSpaceType == ActionSpaceType.Discrete && action.Value != -1 && action.Value != 0 && action.Value != 1)
                    throw new System.InvalidOperationException("A discrete controller must return LEFT, NONE or RIGHT.");
                ApplyAction(action, Time.fixedDeltaTime);
            }
            catch (System.Exception exception) { ResearchMode.Instance.Fail(exception); }
        }
    }
    public void ApplyAction(SteeringAction action, float deltaTime)
        => ApplyDegreesPerSecond(action.Value * ResearchDegreesPerSecond, deltaTime);
    public void ApplyDegreesPerSecond(float degreesPerSecond, float deltaTime)
    {
        var game = GameManager.Instance;
        game.rotationAmount = degreesPerSecond * deltaTime;
        if (game.gamePaused) return;
        float locationSign = game.gameLocation == GameManager.Location.Inside ? 1 : -1;
        transform.Rotate(0, 0, game.rotationAmount * locationSign);
    }
    public void ResetEpisode(Quaternion initialRotation)
    {
        StopAllCoroutines(); CancelInvoke();
        transform.localRotation = initialRotation;
        GameManager.Instance.rotationAmount = 0;
        enabled = true;
    }
}
