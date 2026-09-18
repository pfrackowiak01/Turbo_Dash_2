# Turbo Dash — końcowy raport TEST

Analizę odślepiono dopiero po zapisaniu 3000 poprawnych epizodów. Raport przedstawia fakty liczbowe bez spekulacyjnej interpretacji.

## Protokół i integralność

- 200 seedów TEST × 3 powtórzenia × 5 metod = 3000 poprawnych epizodów; MaxDuration=500 s.
- Jednostka analizy głównej: seed; metryka główna: finalScore.
- Git wykonania: `0fc396934150a94c1521eedbc0dff0f176643a14`; worker SHA-256: `e9656a4844f9670a83297b039b1572c08120edaf3ed4dfadfd28e8ce288184d5`.
- Retry techniczne: 0.

### Zamrożone modele

| Metoda | Model/wersja | Artefakt | SHA-256 |
|---|---|---|---|
| RuleBasedV1 | RuleBasedV1 | `Assets/Turbo_Dash/Code/Research/RuleBasedController.cs` | `e9915f916b22bc5e950b4c87bd3128fed78bbac2ae2e92a5d1083925af80f97e` |
| PPO-D | ppo-discrete-5m-run3, checkpoint 3000000 | `Training/runs/ppo-discrete-5m-run3/best_model/model.zip` | `1b4527e05914ba0269da4a49b0695216469f10a7930ffddd1501cd1a3b607fb1` |
| PPO-C | ppo-continuous-5m-run3, checkpoint 2000004 | `Training/runs/ppo-continuous-5m-run3/best_model/model.zip` | `f2eb8e2464abd8719c9c624523032f0e74886695dede270edfa1c56fd5e9236e` |
| NEAT-D | neat-discrete-v2-200g-run3, generation 141, genome 8134 | `Training/runs/neat-discrete-v2-200g-run3/selected_models/best_200_generations/genome.pkl` | `15a146d9079359210d6552a921d3776a7be5db98541030abe8e8992b9a24d547` |
| NEAT-C | neat-continuous-v1-200g-run1, generation 62, genome 3390 | `Training/runs/neat-continuous-v1-200g-run1/selected_models/best_200_generations/genome.pkl` | `38de5fc3b347cbe71d1cf30a771b9dbbd9c02456b169ed37a54d79e91ec4d2fd` |

## Wynik główny

| Metoda | Średnia finalScore | Mediana | 95% CI bootstrap |
|---|---:|---:|---:|
| PPO-D | 73920.626 | 81669.771 | [70995.616, 76618.063] |
| NEAT-C | 73341.136 | 81644.719 | [69888.249, 76547.999] |
| PPO-C | 66903.718 | 79461.772 | [63223.106, 70395.108] |
| NEAT-D | 32607.619 | 2581.652 | [27800.190, 37410.512] |
| RuleBasedV1 | 31624.463 | 25352.382 | [27001.945, 36340.328] |

Test Friedmana: χ²=308.8832, df=4, p=1.31351e-65.

Brak jednoznacznego zwycięzcy według zamrożonej reguły. Statystycznie nierozdzielny zbiór czołowy: PPO-D, NEAT-C.
PPO-D ma najwyższą wartość numeryczną, lecz nie spełnia warunku jednoznacznej przewagi statystycznej nad czołówką.

## Porównania parami

| A − B | Średnia różnica | 95% CI | p Holm | rank-biserial |
|---|---:|---:|---:|---:|
| RuleBasedV1 − PPO-D | -42296.163 | [-47252.960, -37239.778] | 1.32967e-26 | -0.9014 |
| RuleBasedV1 − PPO-C | -35279.255 | [-40783.964, -29698.844] | 1.83997e-20 | -0.7773 |
| RuleBasedV1 − NEAT-D | -983.155 | [-7275.133, 5335.539] | 0.929994 | -0.0072 |
| RuleBasedV1 − NEAT-C | -41716.673 | [-47381.996, -35798.497] | 2.57987e-23 | -0.8269 |
| PPO-D − PPO-C | 7016.908 | [2642.783, 11557.936] | 0.00520565 | 0.2613 |
| PPO-D − NEAT-D | 41313.008 | [35912.049, 46699.033] | 3.59581e-26 | 0.8796 |
| PPO-D − NEAT-C | 579.490 | [-3842.913, 5095.723] | 0.332917 | -0.1128 |
| PPO-C − NEAT-D | 34296.100 | [28120.053, 40386.460] | 2.62909e-18 | 0.7281 |
| PPO-C − NEAT-C | -6437.418 | [-11058.363, -1809.628] | 3.80448e-05 | -0.3611 |
| NEAT-D − NEAT-C | -40733.518 | [-46188.357, -35093.930] | 6.27741e-26 | -0.8745 |

## Wyniki drugorzędne

| Metoda | Survival [s] | MaxDuration | Kolizje/100 s | Utraty życia/100 s | MaxLevel |
|---|---:|---:|---:|---:|---:|
| PPO-D | 457.188 | 89.500% | 11.419 | 0.265 | 71.767 |
| NEAT-C | 446.506 | 86.833% | 15.344 | 0.265 | 71.670 |
| PPO-C | 426.569 | 82.500% | 6.838 | 0.354 | 65.075 |
| NEAT-D | 241.622 | 40.667% | 10.072 | 1.040 | 32.067 |
| RuleBasedV1 | 227.373 | 38.167% | 7.311 | 1.233 | 31.022 |

Kaplan–Meier jest analizą opisową: `LivesExhausted` jest zdarzeniem, a `MaxDuration` obserwacją prawostronnie cenzurowaną.

## Generalizacja VALIDATION 500 → TEST 500

| Metoda | Validation | TEST | Różnica | Względna |
|---|---:|---:|---:|---:|
| RuleBasedV1 | niedostępne | 31624.463 | — | — |
| PPO-D | 74890.256 | 73920.626 | -969.630 | -1.29% |
| PPO-C | 72340.235 | 66903.718 | -5436.517 | -7.52% |
| NEAT-D | 39742.598 | 32607.619 | -7134.979 | -17.95% |
| NEAT-C | 63393.311 | 73341.136 | 9947.825 | 15.69% |

## Strategia i powtarzalność

Pełne znormalizowane metryki strategii i telemetria akcji znajdują się w CSV. Niedeterministyczność obejmuje rozrzut trzech powtórzeń, wariancję między seedami i ICC; nie wpływa na wybór zwycięzcy.

## Artefakty

Surowe epizody są w `raw/final_test_episodes.csv`, a tabele w katalogu głównym i `analysis/`.

Wykresy PNG 300 dpi:

- [`01_finalScore_violin_box.png`](plots/01_finalScore_violin_box.png)
- [`02_finalScore_ecdf.png`](plots/02_finalScore_ecdf.png)
- [`03_survivalTime_violin_box.png`](plots/03_survivalTime_violin_box.png)
- [`04_survival_kaplan_meier.png`](plots/04_survival_kaplan_meier.png)
- [`05_maxDuration_success_rate.png`](plots/05_maxDuration_success_rate.png)
- [`06_pairwise_finalScore_difference_forest.png`](plots/06_pairwise_finalScore_difference_forest.png)
- [`07_method_seed_heatmap.png`](plots/07_method_seed_heatmap.png)
- [`08_collision_and_life_loss_rates.png`](plots/08_collision_and_life_loss_rates.png)
- [`09_bonus_strategy_rates.png`](plots/09_bonus_strategy_rates.png)
- [`10_discrete_action_profiles.png`](plots/10_discrete_action_profiles.png)
- [`11_continuous_steering_profiles.png`](plots/11_continuous_steering_profiles.png)
- [`12_validation_vs_test_generalization.png`](plots/12_validation_vs_test_generalization.png)
- [`13_repeat_variability.png`](plots/13_repeat_variability.png)
- [`14_hardest_test_seeds.png`](plots/14_hardest_test_seeds.png)
- [`15_failure_overlap_heatmap.png`](plots/15_failure_overlap_heatmap.png)
