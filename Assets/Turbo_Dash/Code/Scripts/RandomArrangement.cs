using TurboDash.Research;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class RandomArrangement : MonoBehaviour
{
    private float angle = 45f;

    private bool initialized;
    void Start() { Initialize(); }

    public void Initialize()
    {
        if (initialized) return;
        initialized = true;
        // Losuje k¹t obrotu kolumny: 
        float randomAngle = GameplayRandom.Range(0, 7) * angle;

        // Obraca obiekt w zale¿noœci od wylosowanego k¹ta
        transform.Rotate(0f, 0f, randomAngle);
    }
}
