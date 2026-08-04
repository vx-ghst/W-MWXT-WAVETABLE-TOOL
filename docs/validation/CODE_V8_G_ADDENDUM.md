# CODE V8-G — Réconciliation normative et transitions

## Baseline et portée

- branche : `code-v8-wavetable-builder` ;
- commit de départ : `030664cfec04c7d36a2726fbb83801486c80f503` ;
- version publique conservée : `0.7.0` ;
- aucune preuve matérielle revendiquée ;
- aucune ouverture de port MIDI, aucun SysEx et aucune allocation mémoire XT.

V8-G traite `CDC-W61-003` à `CDC-W61-006` et `CDC-TRN-001` à
`CDC-TRN-007`. Factory Style reste V8-H, la consolidation 61→N reste V8-I,
l’inventaire/allocation reste V8-J et WCTD/package/matériel reste V8-K.

## Crosswalk canonique

Les 21 labels historiques `CDC-INT-*`, `CDC-FAC-*`, `CDC-WCTD-*` et
`CDC-HWG-*` sont des aliases de migration fermés. Ils ne créent aucune
nouvelle exigence dans le registre 206/206. `CDC-WCTD-003` est reconnu comme
label interne sans revendication CDC. Tout identifiant inconnu est rejeté.

## Budget global des 61 positions

`AdaptiveSlotBudgetPlan` répartit exactement 61 positions logiques entre les
régions actives de `RegionInterestAnalysis`.

| Signal | Poids |
|---|---:|
| poids d’allocation source | 0,20 |
| intérêt | 0,25 |
| changement utile | 0,30 |
| complexité | 0,15 |
| saturation | 0,05 |
| bonus d’attaque | 0,05 |

Une zone stable reçoit une pénalité de 35 %, une zone redondante une pénalité
de 80 %, et une région `REDUNDANCY` ne peut jamais être simultanément marquée
comme forte évolution. V8-G produit ce budget ; son application au placement
musical appartient à V8-H.

## Méthode unique par intervalle

Pour chaque paire de keyframes adjacentes :

1. les familles autorisées sont évaluées ;
2. une seule méthode est sélectionnée ;
3. cette méthode reste immutable dans tout l’intervalle ;
4. seuls les progrès changent d’une position à l’autre ;
5. la décision, les oracles et leurs hashes sont sérialisés.

Lorsque la sélection adaptative est désactivée, la première méthode activée
dans la priorité de la politique est utilisée dans l’intervalle complet.

## Solveur perceptuel et oracles

La famille perceptuelle utilise une inversion déterministe de longueur d’arc
sur une grille impaire de 17 points. Le progrès résolu est conservé seulement
s’il améliore l’erreur cumulative d’au moins `1e-6`. Les autres familles
conservent leur progrès direct mais reçoivent les mêmes oracles quantitatifs.

| Oracle | Poids | Minimum |
|---|---:|---:|
| objectif moyen | 0,35 | — |
| régularité perceptuelle | 0,25 | 0,50 |
| trajet spectral | 0,15 | 0,45 |
| trajet harmonique H1–H3 | 0,15 | 0,70 |
| protections | 0,10 | 0,50 |

Un fallback reste explicitement signalé ; il ne constitue jamais un PASS
silencieux.

## Protections après projection et quantification

La protection RMS et fondamentale est conjointe : la composante fondamentale
est traitée séparément de l’énergie résiduelle orthogonale. Après quantification
XT, un fallback waveform ne remplace le candidat que s’il réduit strictement
la violation normalisée. La plage produite reste `-127..127` ; `-128` n’est
jamais généré.

## Réparation de continuité

La réparation :

- cible uniquement les positions intérieures de transition ;
- ne touche jamais une position verrouillée ou structurelle ;
- mesure le rapport complet avant et après ;
- accepte uniquement une amélioration stricte des échecs, avertissements,
  minimum et moyenne ;
- conserve la sortie originale si le candidat n’améliore pas le rapport.

## Compatibilité

Les modules XT/V7 gelés ne sont pas modifiés. Les sorties V8-A à V8-F restent
lisibles et aucun hash historique n’est recalculé avec une nouvelle
signification. La version reste `0.7.0` jusqu’à V8-L.
