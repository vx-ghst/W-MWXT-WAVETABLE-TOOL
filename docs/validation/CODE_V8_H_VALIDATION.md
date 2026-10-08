# CODE V8-H — Plan et résultats de validation

## Baseline

- branche : `code-v8-wavetable-builder` ;
- commit : `159217a3a3a25b91e2b4a703d41de9253b14d3b3` ;
- PR #7 : ouverte et brouillon au démarrage ;
- commit, push, merge et tag V8-H : aucun pendant l’implémentation locale.

## Gates fonctionnels

1. trois zones non chevauchantes `01–20`, `21–45`, `46–61` ;
2. poids de profils et objectifs normalisés ;
3. budget V8-G consommé par le placement ;
4. locks requis et chronologie requis préservés ;
5. conflits impossibles rejetés sans sortie partielle ;
6. variantes comparées avec scores et deltas visibles ;
7. `factory_style=False` byte-identical au chemin V8-G ;
8. shaping renommé, séparé et optionnel ;
9. aucune prétention de reconstruction historique ;
10. aucun objet V8-I/J/K matérialisé.

## Validation exécutée

Les résultats définitifs sont inscrits par le bundle d’automatisation après :

- tests V8-H ciblés ;
- non-régression V8-F et V8-G ;
- suite publique complète ;
- `compileall` ;
- `git diff --check` ;
- comparaison byte-identical des six modules XT/V7 gelés ;
- construction et inspection de la roue de validation ;
- scan de fuite de données privées.

Les dumps privés, preuves matérielles et captures audio restent hors Git. V8-H
ne revendique aucun PASS matériel.
