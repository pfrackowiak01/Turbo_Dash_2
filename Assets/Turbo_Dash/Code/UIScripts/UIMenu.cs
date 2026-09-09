using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;
using UnityEngine.UI;

public class UIMenu : MonoBehaviour
{
    public TextMeshProUGUI highscoreText;
    public TextMeshProUGUI gameModeText;

    public SaveAndLoadManager saveManager = SaveAndLoadManager.Instance;

    void Start()
    {
        saveManager = SaveAndLoadManager.Instance;
        saveManager.LoadHighScores();
    }

    void Update()
    {
        highscoreText.text = "HighScore: " + saveManager.usedGameMode.HighScore;
        gameModeText.text = "Gamemode: " + saveManager.usedGameMode.GameModeName;
    }

    public void NextGameMode()
    {
        AudioSystem.Instance.PlayButtonSound();

        // Nadpisuje aktualnie u¿ywany GameMode tym o 1 wy¿szym indeksie, jeœli takiego nie ma to wraca na tryb o zerowym indeksie
        if (saveManager.usedGameMode.Index + 1 >= saveManager.allGameModes.Length) saveManager.usedGameMode = saveManager.allGameModes[0];
        else saveManager.usedGameMode = saveManager.allGameModes[saveManager.usedGameMode.Index + 1];
    }

    public void PreviousGameMode()
    {
        AudioSystem.Instance.PlayButtonSound();

        // Nadpisuje aktualnie u¿ywany GameMode tym o 1 ni¿szym indeksie, jeœli takiego nie ma to ustawia na tryb o ostatnim indeksie
        if (saveManager.usedGameMode.Index - 1 < 0) saveManager.usedGameMode = saveManager.allGameModes[saveManager.allGameModes.Length - 1];
        else saveManager.usedGameMode = saveManager.allGameModes[saveManager.usedGameMode.Index - 1];
    }
}
