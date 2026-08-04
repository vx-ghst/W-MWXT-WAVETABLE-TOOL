# CODE V8-J — Validation d’inventaire et d’allocation sûre

## Baseline

```text
Branche : code-v8-wavetable-builder
Commit  : 8bdee0b239277a9ca91a3f4057e3df2e40145cbe
Étape précédente : CODE V8-I
```

## Périmètre validé

- ingestion de dumps externes strictement parsés ;
- inventaire canonique de 250 User Waves et 32 User Wavetables ;
- fusion de preuves identiques et conservation explicite des conflits ;
- états `USED`, `SAFE_FREE`, `ORPHANED`, `UNKNOWN` ;
- interdiction d’inférer `SAFE_FREE` sans couverture et signature matérielle ;
- sélection manuelle de la destination User Wavetable ;
- proposition déterministe de `N` destinations User Wave ;
- préférence pour un bloc contigu ;
- allocation non contiguë uniquement par politique explicite ;
- autorisation d’écrasement par numéro exact ;
- statut `BLOCKED` en cas de capacité sûre insuffisante ;
- agrégat public `build_code_v8j` ;
- aucune WCTD, aucun SysEx, aucun MIDI et aucune écriture mémoire.

## Gates ciblés

```text
modèles inventaire 250/32                         : PASS
hashes et sérialisation déterministes             : PASS
couverture partielle => UNKNOWN                   : PASS
référence observée => USED                        : PASS
couverture complète sans signature => ORPHANED    : PASS
signature validée + couverture => SAFE_FREE       : PASS
conflits => UNKNOWN ou USED prouvé                 : PASS
bloc contigu SAFE_FREE préféré                     : PASS
non-contigu sans opt-in => BLOCKED                 : PASS
overwrite ORPHANED/USED par numéro exact           : PASS
UNKNOWN jamais sélectionné                         : PASS
insuffisance => BLOCKED sans fallback              : PASS
User Wavetable choisie manuellement                : PASS
agrégat V8-J prêt ou bloqué sans sortie partielle  : PASS
API publique et overlay de conformité              : PASS
```

## Validation privée attendue

Lorsqu’un répertoire privé est monté, le gate recherche un dump contenant :

```text
250 USER_WAVE
32 USER_WAVETABLE
```

Il doit prouver la couverture des deux espaces. En l’absence de signature vide
matériellement validée, le même dump doit conserver :

```text
SAFE_FREE = 0
UNKNOWN   = 0 si la couverture est complète et non conflictuelle
USED/ORPHANED uniquement
```

Cette preuve ferme le parsing et la complétude logicielle, mais **n’active pas
SAFE_FREE**. L’activation reste un gate matériel V8-K.

## Non-régression

Les gates V8-I, V8-H, V8-G, V8-D, V8-F, la suite publique complète, les tests
historiques V1/V2 d’allocation/destinations/sécurité, `compileall`, la roue et
les six modules V7 gelés doivent rester PASS avant matérialisation.

## Verdict attendu

```text
CODE V8-J software contract : PASS
SAFE_FREE software inference : DISABLED WITHOUT PROOF
WCTD/materialization/package : NOT STARTED
SysEx/MIDI/memory write       : NONE
V8-K                          : NOT STARTED
```
