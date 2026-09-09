using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

public class LevelLoader : MonoBehaviour
{
    public Animator transition;
    public float transitionTime = 1f;
    public int menuSceneIndex = 0;
    public int gameplaySceneIndex = 1;
    public int shopSceneIndex = 2;
    public int customizationSceneIndex = 3;
    public int skillTreeSceneIndex = 4;
    public int leaderboardSceneIndex = 5;

    // =====================> HOME <=====================
    public void PlayButtonClicked()
    {
        StartCoroutine(LoadLevel(gameplaySceneIndex));
        if (GameManager.Instance != null) GameManager.Instance.RestartGame();
    }

    public void ShopButtonClicked()
    {
        AudioSystem.Instance.PlayButtonSound();
        StartCoroutine(LoadLevel(shopSceneIndex));
    }

    public void CustomizationButtonClicked()
    {
        AudioSystem.Instance.PlayButtonSound();
        StartCoroutine(LoadLevel(customizationSceneIndex));
    }

    public void MenuButtonClicked()
    {
        AudioSystem.Instance.PlayButtonSound();
        StartCoroutine(LoadLevel(menuSceneIndex));
    }

    public void SkillTreeButtonClicked()
    {
        AudioSystem.Instance.PlayButtonSound();
        StartCoroutine(LoadLevel(skillTreeSceneIndex));
    }

    // =====================> GAME <=====================
    public void StartGameButton()
    {
        AudioSystem.Instance.PlayButtonSound();
        GameManager.Instance.ResetGyroscopeRotation();
        GameManager.Instance.gameStart = false;
        TimeManager.Instance.TogglePauseGame();
    }

    public void GoBackToHomeView()
    {
        AudioSystem.Instance.StartPlayMenuMusic();
        TimeManager.Instance.ResetTimeScale();
        MenuButtonClicked();
    }

    public void ContinueGameButton()
    {
        AudioSystem.Instance.PlayButtonSound();
        GameManager.Instance.gameHasEnded = false;
        GameManager.Instance.playerLives = 1;
        TimeManager.Instance.ResetTimeScale();
        GameManager.Instance.ImmortalityEffect();
    }

    public void RetryGameButton()
    {
        AudioSystem.Instance.PlayButtonSound();
        GameManager.Instance.RestartGame();
    }

    public void ResetGyroscopeRotationButton()
    {
        AudioSystem.Instance.PlayButtonSound();
        GameManager.Instance.ResetGyroscopeRotation();
    }

    public void TogglePauseButton()
    {
        AudioSystem.Instance.PlayButtonSound();
        TimeManager.Instance.TogglePauseGame();
    }

    public void TurnOnTURBO()
    {
        AudioSystem.Instance.PlayButtonSound();
        GameManager.Instance.TurboEffect();

    }

    // ==============> ANIMACJA PRZEJŒCIA <==============
    IEnumerator LoadLevel(int levelIndex)
    {
        // Animacja zanikania
        transition.SetTrigger("StartCrossfade");

        // Zaczekanie
        yield return new WaitForSeconds(transitionTime);

        // £adowanie Sceny
        SceneManager.LoadScene(levelIndex);
    }

}
