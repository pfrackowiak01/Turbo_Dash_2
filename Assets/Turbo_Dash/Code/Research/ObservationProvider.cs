using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace TurboDash.Research
{
    public sealed class ObservationFrame
    {
        public const int SchemaVersion = 1;
        public readonly float[] Vector;
        public ObservationFrame(float[] vector) { Vector = vector; }
    }

    // Fixed schema; all data comes from game state, transforms and collider geometry.
    // No camera, rays or future generator draws. See ML_RESEARCH_ENVIRONMENT.md.
    public sealed class ObservationProvider
    {
        public const int TubeCount = 3, HazardCapacity = 32, BonusCapacity = 40;
        public const int GlobalSize = 8, TubeHeaderSize = 3, HazardSize = 16, BonusSize = 9;
        public const int TubeSize = TubeHeaderSize + HazardCapacity * HazardSize + BonusCapacity * BonusSize;
        public const int VectorSize = GlobalSize + TubeCount * TubeSize;
        private readonly ResearchMode research;
        private readonly PlayerCollision player;
        private readonly UIGame ui;
        public ObservationProvider(ResearchMode research, PlayerCollision player, UIGame ui)
        { this.research = research; this.player = player; this.ui = ui; }

        private static float SignedUnit(float value) => value / (1 + Mathf.Abs(value));
        private float Distance(float z) => Mathf.Clamp01((z - player.transform.position.z) / 240f);
        private float Relative(float radians)
        {
            float playerAngle = Mathf.Atan2(player.transform.position.y, player.transform.position.x);
            return (radians - playerAngle) * (GameManager.Instance.gameLocation == GameManager.Location.Inside ? 1 : -1);
        }
        public ObservationFrame Capture()
        {
            var game = GameManager.Instance;
            var vector = new float[VectorSize];
            vector[0] = game.playerLives / (float)game.maxPlayerLives;
            vector[1] = game.playerShield ? 1 : 0;
            vector[2] = ui.turboSlider.value;
            vector[3] = game.turboEffectEnable ? 1 : 0;
            vector[4] = game.playerImmortality ? 1 : 0;
            vector[5] = game.tubeMoveSpeed / (50 + game.tubeMoveSpeed);
            vector[6] = game.gameLocation == GameManager.Location.Outside ? 1 : 0;
            vector[7] = game.gameLevel / (1 + game.gameLevel);
            var tubes = research.Segments.Where(tube => tube && tube.gameObject.activeInHierarchy &&
                tube.transform.position.z + game.tubeLength / 2 >= player.transform.position.z)
                .OrderBy(tube => tube.transform.position.z).ThenBy(tube => tube.Sequence).Take(TubeCount).ToArray();
            float radius = new Vector2(player.transform.position.x, player.transform.position.y).magnitude;
            for (int tubeIndex = 0; tubeIndex < tubes.Length; tubeIndex++)
            {
                int offset = GlobalSize + tubeIndex * TubeSize;
                vector[offset] = 1;
                vector[offset + 1] = Distance(tubes[tubeIndex].transform.position.z - game.tubeLength / 2);
                int hazards = 0, bonuses = 0;
                // Unity hierarchy/component order is stable; avoid GetInstanceID sorting across runs.
                foreach (var collider in tubes[tubeIndex].GetComponentsInChildren<Collider>())
                {
                    if (!collider.enabled || collider.bounds.max.z < player.transform.position.z) continue;
                    if (collider.CompareTag("Portal")) { vector[offset + 2] = 1; continue; }
                    if (ResearchSegment.IsHazard(collider))
                    {
                        bool approximate;
                        var spans = CircularGeometry.Spans(collider, radius, out approximate);
                        // A moving hazard can be temporarily clear of the orbit. Keep its state visible.
                        if (spans.Count == 0) spans.Add(new Vector2(Mathf.Atan2(collider.bounds.center.y, collider.bounds.center.x), 0));
                        foreach (var span in spans)
                        {
                            if (hazards >= HazardCapacity) throw new InvalidOperationException("Observation hazard capacity exceeded. Revise/version schema.");
                            int row = offset + TubeHeaderSize + hazards++ * HazardSize;
                            float angle = Relative(span.x);
                            vector[row] = 1;
                            vector[row + 1] = collider.CompareTag("Wall") ? 1 : 0;
                            vector[row + 2] = collider.CompareTag("Obstacle") ? 1 : 0;
                            vector[row + 3] = Mathf.Sin(angle); vector[row + 4] = Mathf.Cos(angle);
                            vector[row + 5] = span.y / (2 * Mathf.PI);
                            vector[row + 6] = Distance(collider.bounds.min.z);
                            var motion = collider.GetComponentInParent<ObstacleMovement>();
                            if (motion)
                            {
                                vector[row + 7] = motion.isSideToSide || motion.isUpAndDown || motion.isRotating ? 1 : 0;
                                float sidePhase = ResearchMode.GameplayTime * motion.movementSpeedSide;
                                float upPhase = ResearchMode.GameplayTime * motion.movementSpeedUpDown;
                                vector[row + 8] = motion.isSideToSide ? SignedUnit(Mathf.Cos(sidePhase) * motion.movementSpeedSide * motion.movementRangeSide) : 0;
                                vector[row + 9] = motion.isUpAndDown ? SignedUnit(Mathf.Cos(upPhase) * motion.movementSpeedUpDown * motion.movementRangeUpDown) : 0;
                                vector[row + 10] = motion.isRotating ? SignedUnit(motion.rotationSpeed / 360f) : 0;
                                if (motion.isSideToSide) { vector[row + 11] = Mathf.Sin(sidePhase); vector[row + 12] = Mathf.Cos(sidePhase); }
                                if (motion.isUpAndDown) { vector[row + 13] = Mathf.Sin(upPhase); vector[row + 14] = Mathf.Cos(upPhase); }
                            }
                            vector[row + 15] = approximate ? 1 : 0;
                        }
                    }
                    else
                    {
                        int type = BonusIndex(collider.tag);
                        if (type < 0) continue;
                        if (bonuses >= BonusCapacity) throw new InvalidOperationException("Observation bonus capacity exceeded. Revise/version schema.");
                        int row = offset + TubeHeaderSize + HazardCapacity * HazardSize + bonuses++ * BonusSize;
                        vector[row] = 1; vector[row + 1 + type] = 1;
                        float angle = Relative(Mathf.Atan2(collider.bounds.center.y, collider.bounds.center.x));
                        vector[row + 6] = Mathf.Sin(angle); vector[row + 7] = Mathf.Cos(angle);
                        vector[row + 8] = Distance(collider.bounds.min.z);
                    }
                }
            }
            return new ObservationFrame(vector);
        }
        public static int BonusIndex(string tag)
        {
            switch (tag)
            { case "Heart": return 0; case "Shield": return 1; case "Boost": return 2; case "Gold": return 3; case "Diamond": return 4; default: return -1; }
        }
    }

    public static class CircularGeometry
    {
        // Each pair is (world XY centre angle in radians, angular width in radians).
        // Intersect the player orbit with the collider's centre-depth cross section.
        public static List<Vector2> Spans(Collider collider, float radius, out bool approximate)
        {
            approximate = false;
            if (collider is SphereCollider sphere)
            {
                Vector3 scale = sphere.transform.lossyScale;
                float sphereRadius = sphere.radius * Mathf.Max(Mathf.Abs(scale.x), Mathf.Abs(scale.y), Mathf.Abs(scale.z));
                Vector3 centre = sphere.transform.TransformPoint(sphere.center);
                float distance = new Vector2(centre.x, centre.y).magnitude;
                if (distance + radius <= sphereRadius) return new List<Vector2> { new Vector2(0, 2 * Mathf.PI) };
                if (distance < .00001f || distance > radius + sphereRadius || radius > distance + sphereRadius) return new List<Vector2>();
                float half = Mathf.Acos(Mathf.Clamp((radius * radius + distance * distance - sphereRadius * sphereRadius) / (2 * radius * distance), -1, 1));
                return new List<Vector2> { new Vector2(Mathf.Atan2(centre.y, centre.x), half * 2) };
            }
            Vector3 origin, u, v, halfSize;
            if (collider is BoxCollider box)
            {
                origin = box.transform.InverseTransformPoint(new Vector3(0, 0, box.bounds.center.z)) - box.center;
                u = box.transform.InverseTransformVector(new Vector3(radius, 0, 0));
                v = box.transform.InverseTransformVector(new Vector3(0, radius, 0));
                halfSize = box.size / 2;
                approximate = Mathf.Abs(u.z) + Mathf.Abs(v.z) > .0001f;
            }
            else
            {
                // Mesh/capsule: conservative world AABB, explicitly marked in the observation.
                approximate = true;
                origin = new Vector3(-collider.bounds.center.x, -collider.bounds.center.y, 0);
                u = new Vector3(radius, 0, 0); v = new Vector3(0, radius, 0);
                halfSize = collider.bounds.extents;
            }
            var cuts = new List<float> { 0, 2 * Mathf.PI };
            for (int axis = 0; axis < 3; axis++)
            {
                float amplitude = Mathf.Sqrt(u[axis] * u[axis] + v[axis] * v[axis]);
                if (amplitude < .000001f) continue;
                float phase = Mathf.Atan2(v[axis], u[axis]);
                foreach (float boundary in new[] { -halfSize[axis], halfSize[axis] })
                {
                    float ratio = (boundary - origin[axis]) / amplitude;
                    if (Mathf.Abs(ratio) > 1) continue;
                    float angle = Mathf.Acos(ratio);
                    cuts.Add(Mathf.Repeat(phase + angle, 2 * Mathf.PI));
                    cuts.Add(Mathf.Repeat(phase - angle, 2 * Mathf.PI));
                }
            }
            cuts.Sort();
            var intervals = new List<Vector2>();
            for (int i = 1; i < cuts.Count; i++)
            {
                if (cuts[i] - cuts[i - 1] < .000001f) continue;
                float mid = (cuts[i] + cuts[i - 1]) / 2;
                Vector3 point = origin + u * Mathf.Cos(mid) + v * Mathf.Sin(mid);
                if (Mathf.Abs(point.x) <= halfSize.x + .00001f && Mathf.Abs(point.y) <= halfSize.y + .00001f && Mathf.Abs(point.z) <= halfSize.z + .00001f)
                {
                    if (intervals.Count > 0 && Mathf.Abs(intervals[intervals.Count - 1].y - cuts[i - 1]) < .00001f)
                        intervals[intervals.Count - 1] = new Vector2(intervals[intervals.Count - 1].x, cuts[i]);
                    else intervals.Add(new Vector2(cuts[i - 1], cuts[i]));
                }
            }
            if (intervals.Count > 1 && intervals[0].x < .00001f && intervals[intervals.Count - 1].y > 2 * Mathf.PI - .00001f)
            {
                intervals[0] = new Vector2(intervals[intervals.Count - 1].x - 2 * Mathf.PI, intervals[0].y);
                intervals.RemoveAt(intervals.Count - 1);
            }
            return intervals.Select(interval => new Vector2((interval.x + interval.y) / 2, interval.y - interval.x)).ToList();
        }
    }
}
