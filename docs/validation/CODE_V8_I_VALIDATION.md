# CODE V8-I — Validation

## Fermetures visées

- `CDC-W61-002` — provenance réelle/reconstruite conservée aux niveaux logique et physique ;
- `CDC-W61-007` — métadonnées complètes par slot et agrégées par wave physique ;
- `CDC-USE-001` — nombre distinct final calculé après interpolation/shaping ;
- `CDC-USE-002` — redondance, groupes, ruptures et protection requalifiés sur la table finale ;
- `CDC-USE-003` — transitions revalidées sans changer leur rôle logique ;
- `CDC-USE-004` — données préparées pour V9, exigence non déclarée fermée dans V8.

## Gates obligatoires

1. `61 identiques → N=1` ;
2. `61 distinctes → N=61` ;
3. mapping avant/arrière couvrant exactement les positions `0..60` ;
4. groupes exacts, quasi-identiques, polarité et positions protégées testés ;
5. aucune position protégée perdue ;
6. provenance mixte réelle/reconstruite conservée ;
7. métadonnées minimum/maximum/moyenne et hashes de chaque slot conservés ;
8. classification finale couvrant 61 positions sans chevauchement ;
9. déterminisme des JSON et SHA-256 ;
10. agrégat V8-H → V8-I atomique, sans sortie partielle sur rejet ;
11. régressions V8-G/V8-H et modules V7 gelés ;
12. suite publique complète et tests privés historiques ;
13. roue de validation importable ;
14. aucune fuite de dump, SysEx privé ou preuve matérielle dans Git.

## Valeurs de sécurité

La consolidation exacte est le mode par défaut. La consolidation quasi-identique
reste opt-in et ne peut dépasser les seuils de la politique fournie. La sortie
logique de 61 slots reste immuable ; seules les waves physiques partagées sont
réduites.
