using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class TimeManager : MonoBehaviour
{
    // ===================== SINGLETON =====================
    // Deklaruje w³aœciwoœæ statyczn¹ o nazwie "Instance".
    public static TimeManager Instance { get; private set; }

    // Sprawdza, czy ju¿ istnieje instancja TimeManager.
    // Jeœli nie, ustawia wartoœæ w³aœciwoœci "Instance" na bie¿¹c¹ instancjê (this).
    // Mo¿emy siê do niej odwo³ywaæ przez "TimeManager.Instance".
    private void Awake()
    {
        // Obiekt nie zostanie zniszczony podczas przejœcia miêdzy scenami.
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        // Niszczy nowo utworzony obiekt TimeManager, aby zachowaæ tylko jedn¹ instancje w grze.
        else Destroy(gameObject);
    }
    // =====================================================

    private GameManager gameManager;

    private float timeScaleBeforePause;

    private void Start()
    {
        gameManager = GameManager.Instance;

        ResetTimeScale();

        PauseGame();
    }

    private void Update()
    {
#if UNITY_EDITOR
        // ===================> GAME PAUSE SYSTEM <===================
        // Zatrzymywanie i wznawianie rozgrywki za pomoc¹ "Escape", "Space" lub klikniêcia
        if (Input.GetKeyDown(KeyCode.Escape) || Input.GetKeyDown(KeyCode.Space))
        {
            TogglePauseGame();
        }
        // ===========================================================
#endif
    }

    public void TogglePauseGame()
    {
        if (gameManager.gamePaused)
        {
            ResumeGame();
        }
        else
        {
            PauseGame();
        }
    }

    private void PauseGame()
    {
        gameManager.gamePaused = true;
        timeScaleBeforePause = Time.timeScale;
        Time.timeScale = 0f;
    }

    private void ResumeGame()
    {
        gameManager.gamePaused = false;
        Time.timeScale = timeScaleBeforePause;
    }

    public void ResetTimeScale()
    {
        Time.timeScale = 1f;
        timeScaleBeforePause = 1f;
    }
}
