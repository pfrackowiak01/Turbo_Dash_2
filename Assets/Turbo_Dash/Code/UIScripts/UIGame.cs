using System.Collections;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using TMPro;
using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.UI;
//using UnityEngine.UIElements;

public class UIGame : MonoBehaviour
{
    [Header("Game Screen")]
    public GameObject gameScreen;
    public TextMeshProUGUI scoreText;
    public TextMeshProUGUI speedText;
    public TextMeshProUGUI turboText;
    public TextMeshProUGUI gameModeText;
    public TextMeshProUGUI levelText;
    public TextMeshProUGUI coinsText;
    public TextMeshProUGUI diamondsText;
    public TextMeshProUGUI livesText;
    public Image shield;

    [Header("GameStart Screen")]
    public GameObject gameStartScreen;
    public TextMeshProUGUI gameModeName;
    public TextMeshProUGUI gameModeInfo;
    public Image gameModeIcon;

    [Header("GamePaused Screen")]
    public GameObject gamePausedScreen;

    [Header("GameOver Screen")]
    public GameObject gameOverScreen;
    public GameObject endButtons;
    public GameObject continueButton;
    public TextMeshProUGUI topSpeedText;
    public TextMeshProUGUI recordSpeedText;
    public TextMeshProUGUI youTraveledText;
    public TextMeshProUGUI yourHighScoreText;

    // Obs³uga przycisku i slidera z kontynuowaniem rozgrywki
    public Slider continueProgressBar;
    public float waitTime = 2f;
    private float elapsedTime = 0f;
    private bool chanceToContinue = true;

    [Header("Pop-Ups")]
    public GameObject levelUP;
    public GameObject turboButton;
    public GameObject newHighScore;
    public GameObject gainedShield;
    public GameObject gainedLife;

    [Header("Speed Parameters")]
    public float speed;           // 0
    public float baseSpeed;       // 20
    public float maxSpeed;        // 20
    public float turboSpeed;      // 20
    public float topSpeed;        // 20
    public float updateInterval;  // 0.5 - Co ile sekund ma byæ aktualizowany wynik
    private float previousScore;
    private float previousTime;

    [Header("Turbo Parameters")]
    public Slider turboSlider;
    public float passiveFillRate = 0.01f;  // 1% na sekundê
    public float activeFillAmount = 0.4f;  // 40% za wziêcie gwiazdki

    private bool _showNewHighScoreOnce = true;


    void Start()
    {
        speed = 0;
        baseSpeed = 20;
        maxSpeed = 20;
        turboSpeed = 20;
        topSpeed = 0;
        updateInterval = 0.5f;
        continueProgressBar.value = 1f;
        chanceToContinue = true;

        previousScore = GameManager.Instance.gameScore;
        previousTime = Time.time;

        // Ustawienie wartoœci pocz¹tkowej slidera od Turbo na 0%
        turboSlider.value = 0f;

        // Ukrycie guzika TurboButton na starcie
        turboButton.gameObject.SetActive(false);

        AudioSystem.Instance.StartPlayGameMusic();
    }

    void Update()
    {
        // ==============> EKRAN STARTOWY GRY <=============
        if (GameManager.Instance.gameStart)
        {
            // Pokazanie widoku zatrzymanej gry
            gameStartScreen.SetActive(true);

            // Ukryj widok g³ównej gry
            gameScreen.SetActive(false);

            // Wyœwietlenie pocz¹tkowych informacji o trybie gry
            gameModeName.text = SaveAndLoadManager.Instance.usedGameMode.GameModeName;
            gameModeInfo.text = SaveAndLoadManager.Instance.usedGameMode.InfoText;
            gameModeIcon.sprite = SaveAndLoadManager.Instance.usedGameMode.Icon;
        }
        // ============> EKRAN ZAKOÑCZONEJ GRY <============
        else if (GameManager.Instance.gameHasEnded)
        {
            // Pokazanie widoku zakoñczonej gry
            gameOverScreen.SetActive(true);

            // Wyœwietlenie koñcowego wyniku
            topSpeedText.text = "Top Speed: " + topSpeed.ToString("F2") + " m/s";
            recordSpeedText.text = "Record Speed: " + SaveAndLoadManager.Instance.usedGameMode.HighSpeed.ToString("F2") + " m/s";
            youTraveledText.text = "You Travelled: " + ((int)GameManager.Instance.gameScore).ToString("0") + " m";
            yourHighScoreText.text = "Your HighScore: " + SaveAndLoadManager.Instance.usedGameMode.HighScore + " m";

            // Gracz ma jedn¹ szanse, aby kontynuowaæ jak j¹ ju¿ wykorzysta to przechodzi od razu do koñcowych przycisków
            if (chanceToContinue) StartCoroutine(WaitAndExecute());
            else ShowEndButtons();
        }
        // ============> EKRAN ZATRZYMANEJ GRY <============
        else if (GameManager.Instance.gamePaused)
        {
            // Pokazanie widoku zatrzymanej gry
            gamePausedScreen.SetActive(true);
        }
        // -------------> EKRAN AKTYWNEJ GRY <--------------
        else
        {
            // Ukrycie widoku startowego gry
            gameStartScreen.SetActive(false);

            // Ukrycie widoku zatrzymanej gry
            gamePausedScreen.SetActive(false);

            // Ukrycie widoku zakoñczonej gry
            gameOverScreen.SetActive(false);

            // Wyœwietl widok g³ównej gry
            gameScreen.SetActive(true);

            // Wyœwietl informacje o zdobyciu poziomu (LEVEL UP)
            if (GameManager.Instance.showLevelUP)
            {
                // Przywrócenie domyœlej wartoœci, aby ju¿ nie pokazywaæ Level UP'a
                GameManager.Instance.showLevelUP = false;

                StartCoroutine(ShowPopUP(levelUP, 1f));
            }

            // Wyœwietl informacje o nowym rekordzie (NEW HIGHSCORE)
            if (GameManager.Instance.isNewHighScore && _showNewHighScoreOnce)
            {
                _showNewHighScoreOnce = false;
                StartCoroutine(ShowPopUP(newHighScore, 3f));

            }
        }
        // -------------------------------------------------


        // ===========> OBLICZANIE PRÊDKOŒCI m/s <==========
        float currentScore = GameManager.Instance.gameScore;
        float currentTime = Time.time;

        // Sprawdzamy, czy minê³a wystarczaj¹ca iloœæ czasu do aktualizacji wyniku
        if (currentTime - previousTime >= updateInterval)
        {
            // Obliczamy ró¿nicê w punktach i czasie od ostatniej aktualizacji
            float scoreDifference = currentScore - previousScore;
            float timeDifference = currentTime - previousTime;

            // Obliczamy punkty na sekundê (punkty/s)
            float scorePerSecond = scoreDifference / timeDifference;

            // Wyœwietlamy wynik na ekranie
            speed = scorePerSecond;

            // Aktualizujemy wartoœci poprzednich wyników i czasu
            previousScore = currentScore;
            previousTime = currentTime;
        }
        // ------------ ZAPISYWANIE PRÊDKOŒCI --------------
        if (speed > topSpeed) topSpeed = speed;
        if (topSpeed > SaveAndLoadManager.Instance.usedGameMode.HighSpeed) SaveAndLoadManager.Instance.SaveHighSpeed(topSpeed);
        // =================================================


        // =============> SYSTEM OBS£UGI TURBO <============
        // Wyœwietlenie iloœci Turbo w postaci procentów
        turboText.text = (turboSlider.value * 100).ToString("0") + "%";

        // Slider NIE osi¹gn¹³ 100% wype³nienia
        if (turboSlider.value < 1f)
        {
            // Pasywne uzupe³nianie slidera o 1% co 1 sekundê
            turboSlider.value += passiveFillRate * Time.deltaTime;

            // Ukrycie guzika TurboButton
            turboButton.gameObject.SetActive(false);
        }
        else // Slider osi¹gn¹³ ju¿ 100% wype³nienia
        {
            // Wyœwietlenie guzika TurboButton
            turboButton.gameObject.SetActive(true);

            turboText.text = "READY!";
        }
        // =================================================


        // ============> EKRAN ROZGRYWANEJ GRY <============
        // Wyœwietlanie uzyskanego wyniku
        scoreText.text = ((int)GameManager.Instance.gameScore).ToString("0");

        // Wyœwietlanie aktualnej prêdkoœci
        speedText.text = speed.ToString("F2");

        // Wyœwietlanie aktualnego poziomu
        gameModeText.text = SaveAndLoadManager.Instance.usedGameMode.GameModeName;

        // Wyœwietlanie aktualnego poziomu
        levelText.text = GameManager.Instance.gameLevel.ToString();

        // Wyœwietlanie iloœci z³ota
        coinsText.text = GameManager.Instance.playerCoins.ToString();

        // Wyœwietlanie iloœci diamentów
        diamondsText.text = GameManager.Instance.playerDiamonds.ToString();

        // Wyœwietlanie iloœci ¿yæ
        livesText.text = GameManager.Instance.playerLives.ToString() + "/" + GameManager.Instance.maxPlayerLives.ToString();

        // Wyœwietlanie czy gracz posiada tarcze
        if (GameManager.Instance.playerShield) shield.enabled = true;
        else shield.enabled = false;
        // =================================================
    }

    private IEnumerator WaitAndExecute()
    {
        elapsedTime = 0f;

        // Wyœwietlenie progress baru z mo¿liwoœci¹ kontynuowania gry
        continueButton.SetActive(true);
        endButtons.SetActive(false);

        // Aktualizacja progress baru (odlicza czas do koñca)
        while (elapsedTime < waitTime)
        {
            elapsedTime += Time.deltaTime; // Aktualizujemy czas up³ywaj¹cy

            // Aktualizujemy wartoœæ na pasku postêpu w zakresie od 0 do 1
            continueProgressBar.value = 1f - elapsedTime / waitTime;

            yield return null; // Poczekaj na nastêpn¹ klatkê
        }

        // Po zakoñczeniu oczekiwania
        continueProgressBar.value = 0f; // Ustawiamy wartoœæ na 0, aby pasek postêpu znikn¹³

        ShowEndButtons();
    }

    private IEnumerator passiveDecreasingTurbo()
    {
        while (turboSlider.value > 0f)
        {
            yield return new WaitForSeconds(0.1f); // Czekamy 0.1 sekundy

            // Zmniejszamy wartoœæ slidera o 1% (0.01f)
            turboSlider.value -= passiveFillRate;
        }

        // Pasek wyzerowany - wy³¹czamy efekt turbo
        GameManager.Instance.TurnOffTurboEffect();
    }

    // --------------------------------------------------------
    // --------------------- FUNCTIONS ------------------------
    // --------------------------------------------------------
    private void ShowEndButtons()
    {
        // Wyœwietlenie koñcowych przycisków (czas min¹³)
        continueButton.SetActive(false);
        endButtons.SetActive(true);

        // Ukryj widok g³ównej gry
        gameScreen.SetActive(false);

        // Resetowanie szansy na kontynuowanie po œmierci
        chanceToContinue = false;
    }

    public IEnumerator ShowPopUP(GameObject popUp, float seconds)
    {
        // Wyœwietlenie okienka przez okreœlon¹ iloœæ sekund
        popUp.SetActive(true);

        // Poczekaj przez okreœlony czas (w sekundach)
        yield return new WaitForSeconds(seconds);

        // Ukryj obiekt po up³ywie czasu
        popUp.SetActive(false);
    }

    public void AddTurbo()
    {
        // Aktywne uzupe³nienie slidera o wartoœæ activeFillAmount
        turboSlider.value += activeFillAmount;

        // Ograniczenie wartoœci slidera do maksymalnie 100%
        turboSlider.value = Mathf.Clamp01(turboSlider.value);
    }

    public void ResetTurboParameters()
    {
        // Ukrycie guzika TurboButton po aktywacji efektu
        turboButton.gameObject.SetActive(false);

        // Pasywne opró¿nianie slidera o 1% co 0.1 sekundy
        StartCoroutine(passiveDecreasingTurbo());
    }
}
