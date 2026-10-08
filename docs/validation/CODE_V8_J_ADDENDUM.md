# CODE V8-J — Addendum d’inventaire et d’allocation sûre

## Objet

CODE V8-J consomme un `PhysicalWaveSet` V8-I de taille `N`, une User Wavetable
choisie manuellement et un ou plusieurs dumps XT fournis extérieurement. Il
produit un inventaire conservateur des **250 User Waves** et des **32 User
Wavetables**, puis une proposition déterministe de `N` destinations User Wave.

Une source dite « courante » est toujours un fichier capturé extérieurement.
V8-J n’ouvre aucun port MIDI, ne demande aucun dump à l’instrument, n’écrit
aucune mémoire, ne matérialise aucune WCTD et ne génère aucun SysEx.

## États canoniques

```text
USED       une référence WCTD observée prouve l’utilisation
SAFE_FREE  couverture complète et non conflictuelle + signature vide validée matériellement
ORPHANED   contenu présent + couverture complète des références + aucune référence
UNKNOWN    preuve absente, partielle ou conflictuelle
```

Une référence observée suffit à classer `USED`, même si le payload User Wave
est absent ou conflictuel. À l’inverse, l’absence de référence ne devient une
preuve que lorsque les 32 User Wavetables sont toutes couvertes sans conflit.

## Activation de SAFE_FREE

`SAFE_FREE` reste désactivé tant que les conditions suivantes ne sont pas toutes
réunies :

1. couverture complète et non conflictuelle des User Waves `1000–1249` ;
2. couverture complète et non conflictuelle des User Wavetables `097–128` ;
3. signature d’une User Wave vide validée par une preuve matérielle versionnée.

La simple absence de référence, un payload nul ou un dump partiel ne peuvent
jamais être promus implicitement en `SAFE_FREE`.

## Allocation

- la User Wavetable est fournie explicitement par l’utilisateur ;
- le programme propose exactement `N` destinations User Wave ;
- le bloc contigu admissible le plus sûr est préféré ;
- une liste non contiguë exige une politique explicite ;
- `UNKNOWN` est toujours interdit ;
- `USED` et `ORPHANED` exigent l’autorisation explicite de chaque numéro ;
- l’insuffisance de destinations admissibles produit `BLOCKED` ;
- aucun fallback silencieux ou écrasement implicite n’est permis ;
- la proposition expose toutes les waves écrasées et la User Wavetable manuelle.

## Sorties

```text
InventoryDumpSource
InventorySourceEvidence
ValidatedEmptyWaveSignature
InventoryEvidenceStatus
UserWaveInventoryEntry
UserWavetableInventoryEntry
XtMemoryInventory
SafeAllocationPolicy
UserWaveDestinationAssignment
AllocationProposal
CodeV8JAnalysis
```

## Frontières

V8-J ne revendique pas :

- l’activation matérielle de `SAFE_FREE` sans preuve V8-K ;
- la matérialisation WCTD dense ou sparse — V8-K ;
- le package `N WAVD + 1 WCTD` — V8-K ;
- la génération ou transmission SysEx/MIDI ;
- une écriture mémoire XT ;
- une validation matérielle ;
- le rapport utilisateur V9.

Les APIs historiques de `allocation.py`, `destinations.py` et `safety.py`
restent disponibles sans modification de leur contrat. Les six modules XT/V7
gelés restent byte-identical.
