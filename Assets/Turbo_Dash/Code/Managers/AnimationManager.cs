using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class AnimationManager : MonoBehaviour
{
    // ===================== SINGLETON =====================
    // Deklaruje w³aœciwoœæ statyczn¹ o nazwie "Instance".
    public static AnimationManager Instance { get; private set; }

    // Sprawdza, czy ju¿ istnieje instancja AnimationManager.
    // Jeœli nie, ustawia wartoœæ w³aœciwoœci "Instance" na bie¿¹c¹ instancjê (this).
    // Mo¿emy siê do niej odwo³ywaæ przez "AnimationManager.Instance".
    private void Awake()
    {
        // Obiekt nie zostanie zniszczony podczas przejœcia miêdzy scenami.
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        // Niszczy nowo utworzony obiekt AnimationManager, aby zachowaæ tylko jedn¹ instancje w grze.
        else Destroy(gameObject);
    }
    // =====================================================


    // --------------------- PARAMETERS --------------------
    private Animator cameraFollow;


    // --------------------- FUNCTIONS ---------------------
    public void Presets()
    {
        cameraFollow = GameObject.FindWithTag("CameraFollow").GetComponent<Animator>();
        // za wczeœnie
    }

    public void CameraShake()
    {
        cameraFollow = GameObject.FindWithTag("CameraFollow").GetComponent<Animator>();
        cameraFollow.SetTrigger("shake");
    }

    private void Update()
    {
        if (cameraFollow != null)
        {
            cameraFollow = GameObject.FindWithTag("CameraFollow").GetComponent<Animator>();

            // Je¿eli jest w³¹czone TURBO to potrz¹saj lekko kamer¹
            if (GameManager.Instance.turboEffectEnable == true) cameraFollow.SetBool("shakeTurbo", true);
            else cameraFollow.SetBool("shakeTurbo", false);
        }
    }
}
