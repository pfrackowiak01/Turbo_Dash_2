using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class AudioSystem : MonoBehaviour
{

    // ===================== SINGLETON =====================
    // Deklaruje w³aœciwoœæ statyczn¹ o nazwie "Instance".
    public static AudioSystem Instance { get; private set; }

    // Sprawdza, czy ju¿ istnieje instancja AudioSystem.
    // Jeœli nie, ustawia wartoœæ w³aœciwoœci "Instance" na bie¿¹c¹ instancjê (this).
    // Mo¿emy siê do niej odwo³ywaæ przez "AudioSystem.Instance".
    private void Awake()
    {
        // Obiekt nie zostanie zniszczony podczas przejœcia miêdzy scenami.
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        // Niszczy nowo utworzony obiekt AudioSystem, aby zachowaæ tylko jedn¹ instancje w grze.
        else Destroy(gameObject);
    }
    // =====================================================

    [Header("Sources")]
    [SerializeField] private AudioSource sfxSource;
    [SerializeField] private AudioSource musicSource;

    [Header("SFX")]
    public AudioClip sfxButton;
    public AudioClip sfxCoin, sfxDiamond, sfxHeart, sfxShield, sfxBoost, sfxTurbo;
    public AudioClip sfxDestroyObject, sfxDestroyShield, sfxGameOver;

    [Header("Music")]
    public AudioClip gameMusic;
    public AudioClip menuMusic;

    public void Start()
    {
        StartPlayMenuMusic();
    }

    public void PlayButtonSound()
    {
        sfxSource.PlayOneShot(sfxButton);
    }

    public void PlaySound(AudioClip clip)
    {
        sfxSource.PlayOneShot(clip);
    }

    public void ToggleSFX()
    {
        sfxSource.mute = !sfxSource.mute;
    }

    public void ToggleMusic()
    {
        musicSource.mute = !musicSource.mute;
    }

    public void StartPlayGameMusic()
    {
        musicSource.clip = gameMusic;
        musicSource.volume = 0.3f;
        musicSource.Play();
    }

    public void StartPlayMenuMusic()
    {
        musicSource.clip = menuMusic;
        musicSource.volume = 1f;
        musicSource.Play();
    }
}
