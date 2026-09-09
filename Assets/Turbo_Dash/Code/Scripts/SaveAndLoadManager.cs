using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class SaveAndLoadManager : MonoBehaviour
{

    // ===================== SINGLETON =====================
    // Deklaruje w³aœciwoœæ statyczn¹ o nazwie "Instance".
    public static SaveAndLoadManager Instance { get; private set; }

    // Sprawdza, czy ju¿ istnieje instancja SaveAndLoadManager.
    // Jeœli nie, ustawia wartoœæ w³aœciwoœci "Instance" na bie¿¹c¹ instancjê (this).
    // Mo¿emy siê do niej odwo³ywaæ przez "SaveAndLoadManager.Instance".
    private void Awake()
    {
        // Obiekt nie zostanie zniszczony podczas przejœcia miêdzy scenami.
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        // Niszczy nowo utworzony obiekt GameManager, aby zachowaæ tylko jedn¹ instancje w grze.
        else Destroy(gameObject);
    }
    // =====================================================


    // ---------------------- GLOBALS ----------------------

    public GameMode[] allGameModes;
    public GameMode usedGameMode;


    // ----------------- GLOBAL FUNCTIONS ------------------
    void Start()
    {
        // ustawianie domyœlnego gamemoda, je¿eli nie ma ¿adnego wybranego
        if (usedGameMode == null) usedGameMode = allGameModes[0];
    }

    public void SaveHighScore(int highscore)
    {
        if (highscore > allGameModes[usedGameMode.Index].HighScore) allGameModes[usedGameMode.Index].HighScore = highscore;

        switch (usedGameMode.Index)
        {
            case 0:
                if (highscore > allGameModes[0].HighScore) PlayerPrefs.SetInt("gyroscopeHighScore", highscore);
                break;
            case 1:
                if (highscore > allGameModes[1].HighScore) PlayerPrefs.SetInt("touchControlHighScore", highscore);
                break;
            case 2:
                if (highscore > allGameModes[2].HighScore) PlayerPrefs.SetInt("multiplayerHighScore", highscore);
                break;
            default:
                Debug.LogWarning("Nieprawid³owy tryb gry przy próbie zapisu highscora!");
                break;
        }
    }

    public void SaveHighSpeed(float speed)
    {
        if (speed > allGameModes[usedGameMode.Index].HighSpeed) allGameModes[usedGameMode.Index].HighSpeed = speed;

        switch (usedGameMode.Index)
        {
            case 0:
                if (speed > allGameModes[0].HighSpeed) PlayerPrefs.SetFloat("gyroscopeHighSpeed", speed);
                break;
            case 1:
                if (speed > allGameModes[1].HighSpeed) PlayerPrefs.SetFloat("touchControlHighSpeed", speed);
                break;
            case 2:
                if (speed > allGameModes[2].HighSpeed) PlayerPrefs.SetFloat("multiplayerHighSpeed", speed);
                break;
            default:
                Debug.LogWarning("Nieprawid³owy tryb gry przy próbie zapisu prêdkoœci!");
                break;
        }
    }

    public void LoadHighScores()
    {
        allGameModes[0].HighScore = PlayerPrefs.GetInt("gyroscopeHighScore", 0);
        allGameModes[1].HighScore = PlayerPrefs.GetInt("touchControlHighScore", 0);
        allGameModes[2].HighScore = PlayerPrefs.GetInt("multiplayerHighScore", 0);
    }


    public void LoadHighSpeeds()
    {
        allGameModes[0].HighSpeed = PlayerPrefs.GetFloat("gyroscopeHighSpeed", 0);
        allGameModes[1].HighSpeed = PlayerPrefs.GetFloat("touchControlHighSpeed", 0);
        allGameModes[2].HighSpeed = PlayerPrefs.GetFloat("multiplayerHighSpeed", 0);
    }
}
