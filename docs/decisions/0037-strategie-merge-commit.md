# 0037 — Stratégie de merge : merge commit (préserver les références)

## Contexte

Le dépôt fusionnait jusqu'ici **exclusivement en squash** (`allow_squash_merge`
seul activé ; `merge` et `rebase` désactivés ; suppression auto de la branche au
merge). Ce mode condense tous les commits d'une PR en **un seul** sur `main`,
puis **supprime la branche** — donc les SHA des commits d'origine deviennent
inatteignables (aucune réf ne les retient ; ils seront ramassés par le GC).

Deux problèmes concrets, vécus :

1. **Perte de l'historique fin.** Un portage e2e (#173, #197) progresse par
   dizaines de commits porteurs de sens (un drift = un correctif daté). Le
   squash les écrase : `git log`/`git bisect`/`git blame` sur `main` ne voient
   plus qu'un commit monolithique. Le **lien commit ↔ drift corrigé** est perdu.
2. **Commits orphelins en cours de merge.** Comme la branche est supprimée et
   les SHA non préservés, committer sur une branche pendant que sa PR est
   squash-mergée produit des commits **orphelins** (déjà arrivé : récupérés au
   prix d'un `git diff | git apply` sur une branche neuve). Le squash + delete
   rend l'erreur silencieuse.

La CI reflète ce mode : elle valide le **titre de PR** (« sous squash, ce titre
devient le commit sur main ») et **non** les commits individuels.

## Décision

**Fusionner en _merge commit_, en préservant chaque commit de la PR. Le squash
est abandonné comme mode par défaut.**

Concrètement :

1. **Config GitHub** : `allow_merge_commit = true` ;
   `allow_squash_merge = false` ; `allow_rebase_merge = false`. La fusion crée
   un commit de merge qui **relie** la série de commits de la PR à `main`, tous
   conservés tels quels.
2. **Les commits deviennent la matière qualité.** Puisque chaque commit atterrit
   dans `main`, **chaque commit** doit être un Conventional Commit propre (sujet
   minuscule, sans email / `Co-Authored-By`) — règle déjà imposée **localement**
   par le hook lefthook `commit-msg` (commitlint). On exige donc en PR des
   commits soignés, pas seulement un titre soigné.
3. **CI** : la validation du **titre de PR** est remplacée par commitlint sur la
   **plage de commits** de la PR (`--from origin/main --to HEAD`). Le garde-fou
   passe du titre (artefact du squash) aux commits réels.
4. **Suppression de branche** : conservée (`delete_branch_on_merge = true`) —
   sans risque désormais, car les commits sont **référencés par le commit de
   merge** dans `main` (plus d'orphelins après fusion).
5. **Hygiène de PR** : nettoyer sa branche avant merge (regrouper les «
   wip/fixup » par `git commit --amend` / `rebase` **non interactif** local)
   pour que la série versée dans `main` raconte le travail, sans bruit. Pas
   d'historique parfait exigé : un historique **honnête et lisible**.

## Statut

Accepted. (Révise la convention de commits du `CLAUDE.md` et le job
`Validate PR title` de la CI, tous deux écrits pour le squash.)

## Conséquences

- **Gain** : `main` conserve l'historique fin — `git bisect` localise un drift
  au commit près, `git blame` pointe le vrai correctif, chaque SHA reste
  atteignable. Fin de la classe d'incidents « commits orphelins ».
- **Prix à payer** : `main` est plus verbeux (tous les commits de chaque PR +
  commits de merge). C'est le coût assumé de la traçabilité ; `--first-parent`
  donne la vue condensée par PR quand on la veut.
- **Discipline** : chaque commit doit passer commitlint (déjà le cas en local) ;
  la CI le vérifie désormais sur toute la plage. Un « wip » non nettoyé fait
  **échouer la PR** — ce qui pousse à soigner la série avant de demander le
  merge.
- **Migration** : changement de réglage du dépôt (effet immédiat sur les futures
  PR) ; l'historique déjà squashé n'est pas réécrit (honnêteté — on ne refait
  pas le passé, cf. [ADR 0023](0023-plateforme-exemple-generique.md)).
- **Release** : l'outillage de release (Conventional Commits → changelog) lit
  désormais **tous** les commits de `main`, pas un par PR — le changelog gagne
  en granularité (un drift corrigé = une entrée potentielle).
