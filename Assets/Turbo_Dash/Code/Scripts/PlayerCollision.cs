using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SocialPlatforms;

public class PlayerCollision : MonoBehaviour
{
    // ---------------------------------------------------------
    // ---------------------- PARAMETERS ----------------------- 
    // ---------------------------------------------------------

    public EnvironmentMovement environmentMovement;
    private GameManager gameManager;
    private Renderer playerRenderer;
    private GameObject detectedObject;

    public GameObject explosion;
    public GameObject diamondCollectedEffect;
    public GameObject coinCollectedEffect;
    public GameObject heartCollectedEffect;
    public GameObject shieldCollectedEffect;
    public GameObject boostCollectedEffect;


    private Vector3 destroyedObjectPositionInside = new Vector3(0f,-4f,1f);
    private Vector3 destroyedObjectPositionOutside = new Vector3(0f, 6.5f, 1f);

    // ---------------------------------------------------------
    // -------------------- EVENT FUNCTIONS --------------------
    // ---------------------------------------------------------
    void Start()
    {
        gameManager = GameManager.Instance;

        playerRenderer = GetComponent<Renderer>();
        playerRenderer.material = GameManager.Instance.gameTheme.Player;
    }

    private void Update()
    {
        // ^^^^^^^^^^^^^ RĘCZNE USTAWIANIE EFEKTÓW ^^^^^^^^^^^^^
#if UNITY_EDITOR
        if (Input.GetKeyDown(KeyCode.T)) gameManager.TurboEffect();
        if (Input.GetKeyDown(KeyCode.B)) gameManager.BoostEffect();
        if (Input.GetKeyDown(KeyCode.S)) gameManager.ShieldEffect();
        if (Input.GetKeyDown(KeyCode.H)) gameManager.HeartEffect();
        if (Input.GetKeyDown(KeyCode.G)) gameManager.CoinEffect();
        if (Input.GetKeyDown(KeyCode.P)) gameManager.DiamondEffect();
        if (Input.GetKeyDown(KeyCode.L)) gameManager.GameLevelUp();
        if (Input.GetKeyDown(KeyCode.O)) gameManager.playerLives = 1000;
#endif
        // ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

        // Zarządzanie pozycją gracza, gdy jest w środku rury, czy na zewnątrz (Space level)
        if (gameManager.gameLocation == GameManager.Location.Inside) transform.localPosition = new Vector3(0f, -4f, 0f);
        else transform.localPosition = new Vector3(0f, 6.5f, 0f);

        // Wyświetlanie gracza od tego czy żyje i może się poruszać oraz ukrywanie go i blokowanie poruszania się gdy stracił wszystkie życia
        if (gameManager.playerLives > 0)
        {
            playerRenderer.enabled = true;
            environmentMovement.enabled = true;     //można poruszać się na boki
        }
        else
        {
            playerRenderer.enabled = false;
            environmentMovement.enabled = false;    //blokowanie poruszania się na boki
        }
    }

    // |>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<|
    // |>>>>>>>>>>>>>>>>>> COLLISION DETECTION SYSTEM <<<<<<<<<<<<<<<<<<|
    // |>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<|
    private void OnTriggerEnter(Collider collision)
    {
        String inputValueTag = collision.GetComponent<Collider>().tag;
        detectedObject = collision.gameObject;

        if (!gameManager.gameHasEnded) switch (inputValueTag)
        {
            // -------------- STRUCTURES --------------
            case "Wall":
                Debug.Log("Wall detected.");
                LoseLife();
                break;

            case "Obstacle":
                Debug.Log("Obstacle detected.");
                LoseLife();
                break;

            case "Portal":
                Debug.Log("Portal detected.");
                gameManager.isPortalGoingToSpawn = false;
                gameManager.FixScore();
                gameManager.ChangeLocation();
                gameManager.GameLevelUp();
                AudioSystem.Instance.PlaySound(AudioSystem.Instance.sfxBoost);
                AnimationManager.Instance.CameraShake();
                break;

            // ----------------- GEMS -----------------
            case "Boost":
                Debug.Log("Boost gem collected.");
                DestroyDetectedObject();
                PlayVisualEffect(boostCollectedEffect);
                gameManager.BoostEffect();
                break;

            case "Heart":
                Debug.Log("Heart gem collected.");
                DestroyDetectedObject();
                PlayVisualEffect(heartCollectedEffect);
                gameManager.HeartEffect();
                break;

            case "Shield":
                Debug.Log("Shield gem collected.");
                DestroyDetectedObject();
                PlayVisualEffect(shieldCollectedEffect);
                gameManager.ShieldEffect();
                break;

            case "Gold":
                Debug.Log("Gold gem collected.");
                DestroyDetectedObject();
                PlayVisualEffect(coinCollectedEffect);
                gameManager.CoinEffect();
                break;

            case "Diamond":
                Debug.Log("Diamond gem collected.");
                DestroyDetectedObject();
                PlayVisualEffect(diamondCollectedEffect);
                gameManager.DiamondEffect();
                break;

            // -------------- SOMETHING --------------
            default:
                Debug.Log("Something detected?");
                break;
        }
    }
    // |>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<|


    // ---------------------------------------------------------
    // ----------------------- FUNCTIONS -----------------------
    // ---------------------------------------------------------
    private void LoseLife()
    {
        // Sprawdzanie czy gracz jest nieśmiertelny
        if (gameManager.playerImmortality == true || gameManager.turboEffectEnable == true)
        {
            Debug.Log("NIEŚMIERTELNOŚĆ!");
        }
        // Sprawdzenie czy gracz ma tarcze i ją traci
        else if(gameManager.playerShield == true)
        {
            DestroyDetectedObject();
            gameManager.ToggleVisibilityWithTag("VisualEffectShield");
            PlayVisualEffect(shieldCollectedEffect);
            AudioSystem.Instance.PlaySound(AudioSystem.Instance.sfxDestroyShield);
            gameManager.playerShield = false;
            Debug.Log("Tarcza zniszczona");
        }
        // Sprawdzenie czy gracz ma życia i traci jedno
        else if (gameManager.playerLives > 1)
        {
            PlayExplosionEffect();
            DestroyDetectedObject();
            AudioSystem.Instance.PlaySound(AudioSystem.Instance.sfxDestroyObject);
            gameManager.ImmortalityEffect();
            gameManager.playerLives--;
            Debug.Log("Aktualne życia: " + gameManager.playerLives);
        }
        // Jak gracz już nie ma żyć to przegrywa gre
        else
        {
            LoseGame();
        }
    }

    private void LoseGame()
    {
        AudioSystem.Instance.PlaySound(AudioSystem.Instance.sfxGameOver);
        PlayExplosionEffect();
        gameManager.playerLives = 0;
        gameManager.GameOver();
    }

    private void DestroyDetectedObject()
    {
        // Zapamiętaj rodzica wykrytego obiektu
        Transform parent = detectedObject.transform.parent;

        // Sprawdź tag rodzica wykrytego obiektu
        if (parent != null)
        {
            // Jeśli jest przeszkodą to usuń rodzica, a jeśli nie to usuń dziecko
            if (parent.tag == "Obstacle") Destroy(parent.gameObject);
            else Destroy(detectedObject);
        }
    }

    private void PlayExplosionEffect()
    {
        // Efekt potrząśnięcia kamery "Shake"
        AnimationManager.Instance.CameraShake();
        Handheld.Vibrate();

        // Stwórz eksplozje w odpowiednim miejscu
        if (gameManager.gameLocation == GameManager.Location.Inside)
        Instantiate(explosion, destroyedObjectPositionInside, Quaternion.identity);
        else Instantiate(explosion, destroyedObjectPositionOutside, Quaternion.identity);
    }

    private void PlayVisualEffect(GameObject effect)
    {
        // Stwórz eksplozje w odpowiednim miejscu
        if (gameManager.gameLocation == GameManager.Location.Inside)
            Instantiate(effect, destroyedObjectPositionInside, Quaternion.identity);
        else Instantiate(effect, destroyedObjectPositionOutside, Quaternion.identity);
    }
}
