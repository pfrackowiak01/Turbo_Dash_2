using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace TurboDash.Research
{
    public sealed class ResearchSegment : MonoBehaviour
    {
        public sealed class Hazard
        {
            public Collider[] Colliders;
            public bool Touched, Encountered, Resolved;
        }
        public readonly List<Hazard> Hazards = new List<Hazard>();
        public int Sequence { get; internal set; }
        private bool passed;
        public void Register(GameObject spawned)
        {
            var colliders = spawned.GetComponentsInChildren<Collider>().Where(IsHazard).ToArray();
            if (colliders.Length > 0) Hazards.Add(new Hazard { Colliders = colliders });
        }
        public static bool IsHazard(Collider collider) => collider.CompareTag("Wall") || collider.CompareTag("Obstacle");
        public void Contact(Collider collider)
        {
            var hazard = Hazards.Find(item => item.Colliders.Contains(collider));
            if (hazard == null) return;
            hazard.Touched = true;
            Encounter(hazard);
        }
        private static void Encounter(Hazard hazard)
        {
            if (hazard.Encountered) return;
            hazard.Encountered = true;
            ResearchMode.Instance.Current.obstaclesEncountered++;
        }
        public void Sample(float playerZ)
        {
            if (!passed && transform.position.z + GameManager.Instance.tubeLength / 2 < playerZ)
            { passed = true; ResearchMode.Instance.Current.segmentsPassed++; }
            foreach (var hazard in Hazards)
            {
                if (hazard.Resolved) continue;
                var live = hazard.Colliders.Where(c => c && c.enabled && c.gameObject.activeInHierarchy).ToArray();
                if (live.Length == 0) { hazard.Resolved = true; continue; }
                if (live.Min(c => c.bounds.min.z) <= playerZ) Encounter(hazard);
                if (live.Max(c => c.bounds.max.z) < playerZ)
                {
                    hazard.Resolved = true;
                    if (!hazard.Touched) ResearchMode.Instance.Current.obstaclesAvoided++;
                }
            }
        }
    }
}
