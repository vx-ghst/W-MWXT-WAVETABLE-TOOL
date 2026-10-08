# CODE V8-H — Placement piloté par profil et Factory Style

## Baseline et périmètre

- branche : `code-v8-wavetable-builder` ;
- commit de départ : `159217a3a3a25b91e2b4a703d41de9253b14d3b3` ;
- version publique conservée : `0.7.0` ;
- V8-G reste le moteur de budget, interpolation, oracles et réparation ;
- V8-H traite `CDC-PLC-001` à `CDC-PLC-007` et `CDC-PROF-003`.

V8-H n’effectue aucune consolidation 61→N, aucune allocation mémoire XT,
aucune matérialisation WCTD, aucun SysEx et aucun transport MIDI.

## Définition canonique du Factory Style

Dans CODE V8-H, Factory Style est une convention de placement musical des
keyframes, exécutée avant l’interpolation :

| Zone | Positions affichées | Rôle |
|---|---:|---|
| stable/playable | 01–20 | établissement et contenu immédiatement jouable |
| évolution principale | 21–45 | développement spectral et perceptuel central |
| extrême | 46–61 | saturation, complexité et états limites contrôlés |

Les zones sont strictement non chevauchantes. Le système ne prétend pas
reproduire un algorithme historique ou propriétaire de Waldorf ; les cibles et
poids sont des conventions d’ingénierie versionnées et explicables.

## Placement piloté par profil

`PlacementProfilePolicy` dérive des poids normalisés pour :

- brillance ;
- densité harmonique/perceptuelle ;
- saturation ;
- stabilité des graves ;
- fidélité d’ordre, adjacence, fidélité source et budget de zones.

Les profils `Bass/Sub`, `Lead`, `Pad`, `Bell/FM`, `Vocal/Choir`, `Texture`,
`Drone`, `Percussive` et `Experimental` possèdent des cibles et fractions de
zones sérialisées et hashées. Le budget V8-G issu de `RegionInterestAnalysis`
est combiné avec ces fractions avant le placement.

## Contraintes et variantes

- les locks requis priment sur le profil ;
- les contraintes chronologiques requises ne sont jamais violées ;
- un conflit impossible rejette l’analyse sans sortie partielle ;
- une préférence non honorée reste visible dans les outcomes et warnings ;
- plusieurs variantes V8-D sont reclassées avec des scores de trajectoire,
  adjacence, fidélité source et respect du budget de zones ;
- les deltas de position et candidats déplacés sont conservés.

Quand `factory_style=False`, V8-H conserve le chemin V8-G générique et les
builds restent byte-identical par identifiant de variante.

## Migration du lissage V8-F

Le traitement historiquement nommé `FactoryStyle` en V8-F est renommé
`TransitionShaping` :

- il intervient après interpolation ;
- il reste optionnel ;
- il préserve les keyframes protégées ;
- il ne ferme pas `CDC-PROF-003` ;
- les anciens noms restent des aliases de compatibilité et de migration.

Le chemin canonique V8-H n’active jamais ce shaping implicitement à partir du
drapeau Factory. Il exige `transition_shaping_requested=True` séparément.

## Compatibilité

Les six modules XT/V7 gelés restent byte-identical. Les schémas V8-A à V8-G
restent lisibles, les anciens noms V8-F restent importables et aucun hash
historique n’est recalculé avec une nouvelle signification.
