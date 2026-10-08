# CODE V8-G — Validation du candidat automatisé

## Baseline

- branche : `code-v8-wavetable-builder` ;
- commit : `030664cfec04c7d36a2726fbb83801486c80f503` ;
- commit, push, merge ou tag : aucun ;
- version : `0.7.0` inchangée.

## Validation exécutée avant génération du bundle

```text
28 nouveaux tests V8-G : PASS
43 tests interpolation V8-E : PASS
19 tests builder V8-E hors test historique 61-keyframes : PASS
17 tests continuité V8-E : PASS
20 tests densité V8-E : PASS
20 tests modèles V8-E : PASS
5 tests migrations compliance : PASS
49 tests compliance/API V8-E/F : PASS
compileall : PASS
git diff --check : PASS
```

Le test historique `test_sixty_one_selected_keyframes_need_no_transition_records`
et les tests de stress globaux sont exécutés par le script Windows final sans
limite artificielle de durée. La suite publique complète doit réussir avant
application du patch au dépôt principal.

## Validation privée externe

Les dumps matériels restent exclusivement hors Git. Le script Windows exécute
les quatre tests historiques si `D:\\W-MWXT-PRIVATE-DUMPS` contient les
fichiers attendus et produit un rapport privé séparé dans
`D:\\W-MWXT-V8G-R\\04_PRIVATE_SUITE`. Aucun dump ni hash matériel privé
n’est ajouté au patch.

## Gates du script final

Le script n’applique V8-G au dépôt principal que si :

1. le dépôt est exactement sur le commit de baseline ;
2. les changements locaux éventuels sont uniquement des fins de ligne ;
3. `git apply --check` passe sans `--ignore-whitespace` ;
4. les nouveaux tests, les non-régressions et la suite publique passent ;
5. un second worktree propre accepte exactement le patch final ;
6. aucun fichier privé n’apparaît dans le diff.

Les tests privés historiques sont exécutés si `D:\W-MWXT-PRIVATE-DUMPS`
contient les quatre fichiers requis. Leur absence bloque le futur commit mais
n’autorise jamais une fausse preuve matérielle.
