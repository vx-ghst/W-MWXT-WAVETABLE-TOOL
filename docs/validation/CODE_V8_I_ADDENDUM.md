# CODE V8-I — Addendum de consolidation finale

## Objet

CODE V8-I sépare explicitement les **61 positions logiques** de la wavetable et les
**N User Waves physiques**, avec `1 ≤ N ≤ 61`.

La passe s’exécute après placement, interpolation, réparation de continuité et
éventuel `TransitionShaping`. Elle n’alloue aucune destination XT, ne matérialise
aucune WCTD, ne génère aucun SysEx et n’ouvre aucun port MIDI.

## Politique versionnée

1. Les égalités XT-native exactes sur les 64 échantillons stockés sont
   partageables automatiquement.
2. Les quasi-doublons sont désactivés par défaut. Leur activation exige des
   seuils versionnés sur distance perceptuelle, spectrale, de caractéristiques,
   distance échantillon et corrélation.
3. Une fusion quasi-identique est refusée si elle touche un lock, une position
   essentielle, une rupture, une wave structurelle ou extrême.
4. Une fusion quasi-identique est refusée si elle dépasse la perte d’utilité ou
   la dégradation de continuité autorisée.
5. L’équivalence de polarité est diagnostiquée mais non fusionnée par défaut.
6. Le mapping `61 → N` est déterministe, réversible et conserve la totalité des
   métadonnées et provenances par slot.
7. `CDC-USE-004` produit seulement les données canoniques des positions
   essentielles. Le rapport utilisateur reste explicitement V9.

## Frontières

V8-I ne revendique pas :

- l’inventaire mémoire ou `SAFE_FREE` — V8-J ;
- l’allocation des destinations User Wave — V8-J ;
- les références WCTD denses/sparse — V8-K ;
- le package `N WAVD + 1 WCTD` — V8-K ;
- une validation matérielle — V8-K ;
- le rapport utilisateur des slots essentiels — V9.

Les six modules XT/V7 gelés restent inchangés.
