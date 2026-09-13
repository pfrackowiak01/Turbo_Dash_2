using TurboDash.Research;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.SocialPlatforms.Impl;

public class GameManager : MonoBehaviour
//public class GameManager : Singleton<GameManager>
{

    // ======================= SINGLETON =======================
    // Deklaruje w³aœciwoœæ statyczn¹ o nazwie "Instance".
       public static GameManager Instance { get; private set; }

    // Sprawdza, czy ju¿ istnieje instancja GameManager.
    // Jeœli nie, ustawia wartoœæ w³aœciwoœci "Instance" na bie¿¹c¹ instancjê (this).
    // Mo¿emy siê do niej odwo³ywaæ przez "GameManager.Instance".
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
    
    // =========================================================

    // ---------------------------------------------------------
    // ------------------------ GLOBALS ------------------------
    // ---------------------------------------------------------
    [Header("Game Settings")]
    public bool gameHasEnded;
    public bool gamePaused;
    public bool gameStart;
    public float gameLevel;
    public float spaceLevel;
    public Theme gameTheme;
    public string gameThemeName;
    public LevelDifficulty gameInsideDifficulty;
    public LevelDifficulty gameOutsideDifficulty;
    public Location gameLocation;
    public float restartDelay = 1f;
    public bool isPortalGoingToSpawn;
    public GameObject Portal;
    public Quaternion initialRotation; // ¯yroskop

    [Header("Player Settings")]
    public int maxPlayerLives;
    public int playerLives;
    public bool playerShield;
    public bool playerImmortality;
    public int playerCoins;
    public int playerDiamonds;
    public bool turboEffectEnable;
    public bool isFOVChanging;
    public float rotationAmount;

    [Header("Tube Settings")]
    public int safeTubes;           // 3                              // Iloœæ bezpiecznych rur bez przeszkód na pocz¹tku gry
    public float tubeLength;        // 60                             // D³ugoœæ pojedynczej rury
    public float tubeDeadZone;      // -60                            // Miejsce usuniêcia rury
    public float tubeSpawnZone;     // 240                            // Miejsce pojawienia siê rury
    public float tubeMoveSpeed;     // 50                             // Aktualna prêdkoœæ poruszania siê rury
    public float tubeSpawnRate;     // 1.2                            // Co ile sekund ma siê pojawiaæ nowa rura
    public float startMoveSpeed;    // 50                             // Pocz¹tkowa prêdkoœæ poruszania siê rury
    public float extraMoveSpeed;    // 0                              // Dodatkowa przyspieszenie poruszania siê rury
    public float maxExtraMoveSpeed; // 30                             // Maksymalne dodatkowa przyspieszenie rury

    [Header("Level Generation")]
    public Wall[] allWalls;                                           // Tablica wszystkich œcian
    public Obstacle[] allObstacles;                                   // Tablica wszystkich przeszkód
    public Gem[] allGems;                                             // Tablica wszystkich gemów
    public Theme[] allThemes;                                         // Tablica wszystkich motywów
    public List<Wall> usedWalls = new List<Wall>();                   // Lista aktualnie u¿ywanych œcian
    public List<Obstacle> usedObstacles = new List<Obstacle>();       // Lista aktualnie u¿ywanych przeszkód
    public List<Gem> usedGems = new List<Gem>();                      // Lista aktualnie u¿ywanych gemów

    [Header("Scoring System")]
    public float timer = 0f;
    public float gameScore = 0f;
    public float gameScoreMultiplier = 23f;
    public float gameScoreLevelMultiplier;
    public float distanceToLevelUp = 1000f;
    public float distanceToSpawnPortal = 200f;
    public float distanceToRepeatStage; // 4000f
    public bool showLevelUP = false;                                 // Gdy wartoœæ zmieni siê na true to poka¿e siê okienko z LEVEL UP
    public bool isNewHighScore = false;

    public float firstLevelUP;
    public float secondLevelUP;
    public float thirdLevelUP;
    public float fourthLevelUP;

    [Header("Private Parameters")]
    private UIGame UIGame;
    private AudioSystem audioSystem => AudioSystem.Instance;

    public enum LevelDifficulty
    {
        None,
        Any,
        Easy,
        Medium,
        Hard
    }

    public enum Location
    {
        Inside,
        Outside,
        Both
    }

    // ---------------------------------------------------------
    // -------------------- EVENT FUNCTIONS --------------------
    // ---------------------------------------------------------
    public void Start()
    {
        // Ustawienie pocz¹tkowych wartoœci
        StartGame();

        // Przypisanie odpowiednich obiektów w AnimationManager
        AnimationManager.Instance.Presets();

        // Ustala pocz¹tkow¹ rotacjê telefonu jako referencjê do ¿yroskopu
        ResetGyroscopeRotation();
    }

    public void Update()
    {
        if (ResearchMode.Active && !ResearchMode.Running) return;
        float previousResearchScore = gameScore;
        //  =================== UP£YW CZASU ====================
        if (!gameHasEnded)
        {
            // > Obliczanie premii od aktualnego levela jako dodatkowy mno¿nik punktów.
            // --> za ka¿dy level +10%
            gameScoreLevelMultiplier = (gameLevel + 10f) / 10f;

            // > Obliczanie wyniku z premi¹ od efektu przyspieszenia "Turbo" oraz bez premii.
            // --> efekt Turbo daje punkty x2
            if (turboEffectEnable) timer += (Time.deltaTime * 2 * gameScoreLevelMultiplier * gameScoreMultiplier); 
            else timer += Time.deltaTime * gameScoreLevelMultiplier * gameScoreMultiplier;

            // + Jeœli gra siê nie zakoñczy³a to obliczanie wartoœæ dodawanego wyniku na podstawie czasu
            if (!gameHasEnded) gameScore = timer;
        }
        // =====================================================

        // ^^^^^^^^^^^^^ RÊCZNE USTAWIANIE WYNIKU ^^^^^^^^^^^^^^
        #if UNITY_EDITOR
            if (!ResearchMode.Active && Input.GetKeyDown(KeyCode.Q)) timer += 200f;
            if (!ResearchMode.Active && Input.GetKeyDown(KeyCode.W)) timer = 2000f;
        #endif
        // ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

        // =============> LEVEL UP / SCORE SYSTEM <============= (DZIA£A TYLKO GDY ETAP MA 4 levele)

        // Zwiêkszenie poziomu po okreœlonym pokonanym dystansie
        if (gameScore > firstLevelUP)
        {
            firstLevelUP += distanceToRepeatStage;
            GameLevelUp();
        }
        if (gameScore > secondLevelUP)
        {
            secondLevelUP += distanceToRepeatStage;
            GameLevelUp();
        }
        // Zespawnowanie Portalu na okreœlonym dystansie
        if (!isPortalGoingToSpawn)
        {
            if (gameScore > thirdLevelUP) isPortalGoingToSpawn = true;
            if (gameScore > fourthLevelUP) isPortalGoingToSpawn = true;
        }
        // =====================================================

        if (!ResearchMode.Active && gameScore > SaveAndLoadManager.Instance.usedGameMode.HighScore) isNewHighScore = true;
        if (gameScore != previousResearchScore) ResearchEvents.Emit(ResearchEventType.ScoreDelta, gameScore - previousResearchScore);
    }

    // ---------------------------------------------------------
    // ------------------ EFFECT FUNCTIONS ---------------------
    // ---------------------------------------------------------
    public void BoostEffect()
    {
        audioSystem.PlaySound(audioSystem.sfxBoost);
        UIGame = GameObject.FindWithTag("UIGame").GetComponent<UIGame>();
        UIGame.AddTurbo();
    }

    public void TurboEffect()
    {
        bool started = !turboEffectEnable;
        audioSystem.PlaySound(audioSystem.sfxTurbo);
        UIGame = GameObject.FindWithTag("UIGame").GetComponent<UIGame>();
        UIGame.ResetTurboParameters();

        turboEffectEnable = true;
        isFOVChanging = true;
        ImmortalityEffect();
        ToggleVisibilityWithTag("VisualEffectTurbo");
        if (started) ResearchEvents.Emit(ResearchEventType.TurboActivated);
        
    }

    public void TurnOffTurboEffect()
    {
        turboEffectEnable = false;
        isFOVChanging = true;
        ToggleVisibilityWithTag("VisualEffectTurbo");
    }

    public void HeartEffect()
    {
        audioSystem.PlaySound(audioSystem.sfxHeart);
        UIGame = GameObject.FindWithTag("UIGame").GetComponent<UIGame>();
        if (playerLives < maxPlayerLives) playerLives++;
        if (!ResearchMode.Active) StartCoroutine(UIGame.ShowPopUP(UIGame.gainedLife, 1f));
    }

    public void ShieldEffect()
    {
        audioSystem.PlaySound(audioSystem.sfxShield);
        UIGame = GameObject.FindWithTag("UIGame").GetComponent<UIGame>();
        if (playerShield == false)
        {
            playerShield = true;
            ToggleVisibilityWithTag("VisualEffectShield");
        }
        if (!ResearchMode.Active) StartCoroutine(UIGame.ShowPopUP(UIGame.gainedShield, 1f));
    }

    public void CoinEffect()
    {
        audioSystem.PlaySound(audioSystem.sfxCoin);
        playerCoins++;
        if (!ResearchMode.Active) PlayerPrefs.SetInt("Coins",playerCoins);
    }

    public void DiamondEffect()
    {
        audioSystem.PlaySound(audioSystem.sfxDiamond);
        playerDiamonds++;
        if (!ResearchMode.Active) PlayerPrefs.SetInt("Diamonds", playerDiamonds);
    }

    public void ImmortalityEffect()
    {
        playerImmortality = true;
    }


    // ---------------------------------------------------------
    // ------------------ GLOBAL FUNCTIONS ---------------------
    // ---------------------------------------------------------
    public void FixScore()
    {
        // Rozró¿nienie przy jakim portalu gameScore nale¿y naprawiæ
        if (thirdLevelUP < fourthLevelUP)
        {
            // Je¿eli wynik jest mniejszy od planowanego Scora na level to doci¹gnij wynik scora
            if (timer < thirdLevelUP + distanceToSpawnPortal) timer = thirdLevelUP + distanceToSpawnPortal;
            // Zwiêkszenie do kolejnego progu aby wbiæ level
            thirdLevelUP += distanceToRepeatStage;
        }
        else
        {
            // Je¿eli wynik jest mniejszy od planowanego Scora na level to doci¹gnij wynik scora
            if (timer < fourthLevelUP + distanceToSpawnPortal) timer = fourthLevelUP + distanceToSpawnPortal;
            // Zwiêkszenie do kolejnego progu aby wbiæ level
            fourthLevelUP += distanceToRepeatStage;
        }
    }

    public void StartGame()
    {
        gameHasEnded = false;
        gamePaused = true;
        gameStart = true;
        gameLevel = 1;
        spaceLevel = 4;
        gameInsideDifficulty = LevelDifficulty.Easy;
        gameOutsideDifficulty = LevelDifficulty.Hard;
        gameLocation = Location.Inside;
        isPortalGoingToSpawn = false;

        playerCoins = ResearchMode.Active ? 0 : PlayerPrefs.GetInt("Coins", 0);
        playerDiamonds = ResearchMode.Active ? 0 : PlayerPrefs.GetInt("Diamonds", 0);
        maxPlayerLives = 3;
        playerLives = maxPlayerLives;
        playerShield = false;
        playerImmortality = false;
        turboEffectEnable = false;
        isFOVChanging = false;
        rotationAmount = 0;

        safeTubes = 3;
        tubeLength = 60f;
        tubeDeadZone = -tubeLength;
        tubeSpawnZone = tubeLength * 4f;
        startMoveSpeed = 50f;
        tubeMoveSpeed = startMoveSpeed;
        tubeSpawnRate = tubeLength / tubeMoveSpeed;
        extraMoveSpeed = 0f;
        maxExtraMoveSpeed = 30f;

        usedWalls = UpdateObjectListToSpawnByLevel(allWalls);
        usedObstacles = UpdateObjectListToSpawnByLevel(allObstacles);
        usedGems = UpdateObjectListToSpawnByLevel(allGems);

        gameTheme = GetThemeByName(gameThemeName);
        RenderSettings.skybox = gameTheme.Space;

        timer = 0f;
        gameScore = 0f;
        distanceToRepeatStage = distanceToLevelUp * 4;   // jeden Stage zawiera 4 levele
        firstLevelUP = distanceToLevelUp;                                 // 1000f
        secondLevelUP = distanceToLevelUp * 2;                            // 2000f
        thirdLevelUP = distanceToLevelUp * 3 - distanceToSpawnPortal;     // 3000f - 180f
        fourthLevelUP = distanceToRepeatStage - distanceToSpawnPortal;    // 4000f - 180f

        // Przypisanie odpowiednich obiektów w AnimationManager
        AnimationManager.Instance.Presets();
    }

    public void GameOver()
    {
        if (gameHasEnded == false)
        {
            gameHasEnded = true;
            if (!ResearchMode.Active) Time.timeScale = 0.4f;
            if (!ResearchMode.Active) SaveAndLoadManager.Instance.SaveHighScore((int)gameScore);
            UnityEngine.Debug.Log("GAME OVER");
            //Invoke("RestartGame",restartDelay);
        }
    }

    public void RestartGame()
    {
        // Zresetowanie postêpu                         <----------------- Chyba niepotrzebne!
        usedWalls = new List<Wall>();
        usedObstacles = new List<Obstacle>();
        usedGems = new List<Gem>();
        gameHasEnded = false;

        // Ustawienie pocz¹tkowych wartoœci
        StartGame();

        // Uruchomienie gry od nowa
        SceneManager.LoadScene(1);
    }

    public void GameLevelUp()
    {
        // Zwiêkszenie levelu, definiowanie poziomu
        gameLevel++;
        ChooseGameDifficultyByLocation();

        // Wyœwietlenie okienka z LEVEL UP
        showLevelUP = true;

        // Obliczanie nowej prêdkoœci poruszania siê rur
        if (extraMoveSpeed < maxExtraMoveSpeed) extraMoveSpeed += 5f;
        tubeMoveSpeed = startMoveSpeed + extraMoveSpeed;

        // Korygowanie czasu w jakim rury muszê siê spawnowaæ, aby zachowaæ odpowiedni¹ odleg³oœæ
        tubeSpawnRate = tubeLength / tubeMoveSpeed;

        // Nadpisywanie list nowymi listami dla aktualnego levelu
        usedWalls = UpdateObjectListToSpawnByLevel(allWalls);
        usedObstacles = UpdateObjectListToSpawnByLevel(allObstacles);
        usedGems = UpdateObjectListToSpawnByLevel(allGems);
    }

    public void ChangeLocation()
    {
        if (gameLocation == Location.Inside) gameLocation = Location.Outside;
        else gameLocation = Location.Inside;
        safeTubes = 2;
    }

    public void ChooseGameDifficultyByLocation()
    {
        // SPACE Level - Outside
        if (gameLocation == Location.Outside)
        {
            switch (gameOutsideDifficulty)
            {
                case LevelDifficulty.Easy:
                    gameOutsideDifficulty = LevelDifficulty.Medium;
                    break;
                case LevelDifficulty.Medium:
                    gameOutsideDifficulty = LevelDifficulty.Hard;
                    break;
                case LevelDifficulty.Hard:
                    gameOutsideDifficulty = LevelDifficulty.Easy;
                    break;
            }
        }
        // DEFAULT Level - Inside
        else
        {
            switch (gameInsideDifficulty)
            {
                case LevelDifficulty.Easy:
                    gameInsideDifficulty = LevelDifficulty.Medium;
                    break;
                case LevelDifficulty.Medium:
                    gameInsideDifficulty = LevelDifficulty.Hard;
                    break;
                case LevelDifficulty.Hard:
                    gameInsideDifficulty = LevelDifficulty.Easy;
                    break;
            }
        }
    }

    // Funkcjê z wykorzystaniem parametru typu generycznego, która bêdzie akceptowaæ dowoln¹ klasê implementuj¹c¹ interfejs ISpawnable
    public List<T> UpdateObjectListToSpawnByLevel<T>(T[] allObjects) where T : ISpawnable
    {
        List<T> updatedObjects = new List<T>();

        // Przechodzi przez wszystkie obiekty
        foreach (var obj in allObjects)
        {
            // Sprawdza, czy obiekt ma ten sam poziom trudnoœci i lokacje co aktualny stan gry
            if ((obj.GetLevelDifficulty() == gameInsideDifficulty || obj.GetLevelDifficulty() == LevelDifficulty.Any) &&
                (obj.GetLocation() == gameLocation || obj.GetLocation() == Location.Both))
            {
                // Dodaje obiekt do listy
                updatedObjects.Add(obj);
            }
        }

        return updatedObjects;
    }

    public Theme GetThemeByName(string themeNameToFind)
    {
        // Przeszukujemy wszystkie motywy w poszukiwaniu tej w³aœciwej
        foreach (Theme theme in allThemes)
        {
            if (theme.ThemeName == themeNameToFind) return theme;
        }

        // Jeœli nie znaleziono motywu o podanej nazwie, zwracamy domyœlny motyw
        return allThemes.FirstOrDefault(theme => theme.ThemeName == "Default");
    }

    public void SpawnObject<T>(List<T> objectList, Transform parent) where T : ISpawnable
    {
        if (objectList.Count > 0)
        {
            int randomIndex = GameplayRandom.Range(0, objectList.Count);
            ISpawnable spawnableObject = objectList[randomIndex];
            GameObject newObject = Instantiate(spawnableObject.GetPrefab(), parent.position, parent.rotation, parent);
            AssignMaterialByTag(newObject);
            ResearchMode.RegisterSpawn(newObject, parent);
        }
        else UnityEngine.Debug.Log("Lista obiektów jest pusta!");
    }
    public void SpawnPortal(Transform parent)
    {
        GameObject newObject = Instantiate(Portal, parent.position, parent.rotation, parent);
        //AssignMaterialByTag(newObject);
            ResearchMode.RegisterSpawn(newObject, parent);
    }


    private void AssignMaterialByTag(GameObject obj)
    {
        Renderer renderer = obj.GetComponent<Renderer>();
        Renderer[] childRenderers = obj.GetComponentsInChildren<Renderer>();

        if (renderer != null)
        {
            if (obj.CompareTag("Obstacle")) renderer.material = gameTheme.Obstacle;
            else if (obj.CompareTag("Wall")) renderer.material = gameTheme.Wall;
        }
        else if (childRenderers != null)
        {
            foreach (Renderer childRenderer in childRenderers)
            {
                if (obj.CompareTag("Obstacle")) childRenderer.material = gameTheme.Obstacle;
                else if (obj.CompareTag("Wall")) childRenderer.material = gameTheme.Wall;
            }
        }
    }

    public void ToggleVisibilityWithTag(string tagToToggle)
    {
        GameObject[] objectsToToggle = GameObject.FindGameObjectsWithTag(tagToToggle);

        foreach (GameObject obj in objectsToToggle)
        {
            Renderer renderer = obj.GetComponent<Renderer>();
            if (renderer != null) renderer.enabled = !renderer.enabled;
        }
    }

    public void ResetGyroscopeRotation()
    {
        // W³¹cza ¿yroskop
        Input.gyro.enabled = true;

        // Ustala pocz¹tkow¹ rotacjê telefonu jako referencjê do ¿yroskopu
        initialRotation = Input.gyro.attitude;
    }

}
