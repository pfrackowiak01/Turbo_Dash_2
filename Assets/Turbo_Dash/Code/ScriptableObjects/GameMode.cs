using System.Collections;
using System.Collections.Generic;
using Unity.VisualScripting;
using UnityEngine;

[CreateAssetMenu(fileName = "GameModeData", menuName = "ScriptableObject/GameMode")]
public class GameMode : ScriptableObject
{
    [Header("GameMode parameters")]
    [SerializeField] private int index;
    [SerializeField] private string gameModeName;
    [SerializeField] private string infoText;
    [SerializeField] private Sprite icon;
    [SerializeField] private bool unlocked;
    [SerializeField] private int highScore;
    [SerializeField] private int highLevel;
    [SerializeField] private float highSpeed;

    [Header("GameMode stats")]
    [SerializeField] private int totalCollectedGold;
    [SerializeField] private int totalCollectedDiamonds;
    [SerializeField] private int totalCollectedShields;
    [SerializeField] private int totalCollectedLives;
    [SerializeField] private int totalCollectedBoosts;

    // Hermetyzacja w postaci Enkapsulacji
    public int Index { get => index; set => index = value; }
    public string GameModeName { get => gameModeName; set => gameModeName = value; }
    public string InfoText { get => infoText; set => infoText = value; }
    public Sprite Icon { get => icon; set => icon = value; }
    public bool Unlocked { get => unlocked; set => unlocked = value; }
    public int HighScore { get => highScore; set => highScore = value; }
    public int HighLevel { get => highLevel; set => highLevel = value; }
    public float HighSpeed { get => highSpeed; set => highSpeed = value; }
    public int TotalCollectedGold { get => totalCollectedGold; set => totalCollectedGold = value; }
    public int TotalCollectedDiamonds { get => totalCollectedDiamonds; set => totalCollectedDiamonds = value; }
    public int TotalCollectedShields { get => totalCollectedShields; set => totalCollectedShields = value; }
    public int TotalCollectedLives { get => totalCollectedLives; set => totalCollectedLives = value; }
    public int TotalCollectedBoosts { get => totalCollectedBoosts; set => totalCollectedBoosts = value; }
}
