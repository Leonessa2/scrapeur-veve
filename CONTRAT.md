# CONTRAT — v4 (28/11/2026)

> Ce que le Scrapeur publie et comment le lire. **Fait foi pour tous les
> projets du réseau VeVe.** Toute modification = nouvelle version, annoncée,
> jamais en silence ; on ajoute des champs, on n'en retire pas sans prévenir.
>
> Journal :
> - v4 (28/11/2026, décision de Preda) : section 3.3 — un floor du jour
>   **au-dessus de 15 000 $ ne compte jamais** pour l'ATH/ATL (comme sous
>   1 $), même plusieurs jours de suite ; fiche pas encore sortie : `ath`,
>   `atl` et leurs dates **vides** ; fiche sans relevé : la valeur du tracker
>   reste soumise aux seuils. Mêmes colonnes, rien d'ajouté ni de retiré.
> - v3 (28/11/2026, go de Preda) : section 2 précisée — `elements.csv` ne
>   change pas ; les offres de l'historique de `prices-full` sont vidées aussi.
> - v2 (28/11/2026, go de Preda) : bannières de l'accueil de veve.me
>   (section 5), ajout pur, rien ne change pour les fichiers de la v1.
> - v1 (28/11/2026, go de Preda) : point décimal dans `prices-full` ; nombre
>   d'offres vide = inconnu ; règle du floor du jour, des floors suspects et
>   des ATH/ATL, fichier « floor du jour » ; onglet `📝C-BLOG`.
>
> ⚠️ **Ce qui est écrit ici n'est pas encore entièrement publié.** Les
> fichiers changent dans l'ordre de la section 3.8 : le nombre d'offres vide
> et la règle des floors n'arrivent qu'après les corrections de veveprice,
> et sur un go de Preda.

## Règle générale (rappel de RESEAU.md)
- On ajoute des colonnes, on n'en retire pas sans prévenir.
- Chaque fichier publié porte sa date de collecte.

## 1. prices-full : point décimal obligatoire

**Fichiers :** release `prices-full` de `Leonessa2/jetonveve`
(`prices.csv.gz`, `prices.parquet`, `prices_baselines.csv.gz`).

- Tout nombre s'écrit avec un **point** comme séparateur décimal (`1.95`),
  jamais une virgule (`1,95`), et sans séparateur de milliers (`15000`, pas
  `15 000` ni `15,000`).
- Une valeur qui ne respecte pas cette règle est **refusée à la
  publication** : la tâche s'arrête et alerte, plutôt que de publier un
  nombre douteux ou de le jeter en silence.
- Déjà vrai dans les faits depuis le 26/11 (commit `01544a3`) ; cette règle
  l'écrit noir sur blanc.

## 2. Nombre d'offres : vide = inconnu, 0 = vraiment zéro

**Colonnes :** `listings` de la release `catalogue` et `listings` de
`prices-full` (**historique compris** : toutes les lignes passées sont vidées
aussi, décision de Preda du 28/11/2026).

**`elements.csv` ne change pas** (dépôt `scrapeur-veve`, `data/elements.csv`) :
ni ses offres, ni ses ATH/ATL. Il n'est lu ni par veveprice ni par vevewiki,
mais par `floor-watch.yml` (alertes Discord) et `alertes-audit.yml`
(jetonveve). Le projet Bot décidera plus tard s'il veut les nouvelles valeurs
pour ses alertes (décision de Preda du 28/11/2026).

- **Vide** = on ne sait pas. La source ne donne pas l'information, ou on ne
  lui fait pas confiance.
- **0** = on a vérifié qu'il n'y a aucune offre en vente.
- **Un nombre > 0** = nombre d'offres réellement vu par une source qui le
  mesure.
- Une fiche qui a un floor ne peut pas avoir 0 offre : dans ce cas, on
  écrit **vide**.
- Tant qu'aucune source fiable n'est en place (mesure du 26/11 : le tracker
  ne remplit le champ que pour ~12 % des fiches), la colonne est publiée
  **vide** pour toutes les fiches.
- Les sites doivent afficher « inconnu », et jamais « 0 offre », pour une
  case vide.
- **Ordre de mise en place** : le Scrapeur ne publie le nombre d'offres vide
  **qu'après la mise en ligne** de la correction de veveprice (demande n° 3,
  `correctif/offres-vides-et-collection`), qui aujourd'hui change une case
  vide en 0.

## 3. Floor du jour, ATH et ATL — décidé par Preda le 27/11/2026

> Source : RESEAU.md v3.16, « Règle des floors, ATH et ATL ». But : les
> graphiques montrent le **floor réel de chaque jour** et les **vrais**
> ATH/ATL, jamais faussés par une annonce éclair, un retrait d'annonces ou
> une annonce « troll ».
> ⚠️ Avant toute publication qui applique cette règle, le Scrapeur donne à
> Preda **le nombre de fiches qui changent** (ATH, ATL, points de courbe) :
> c'est ce chiffre qui déclenche son go.

**Fichiers :**
- release `prices-full` de `Leonessa2/jetonveve` : **garde sa forme actuelle
  dans la v1** (une ligne à chaque changement de floor relevé) ;
- **nouveau fichier « floor du jour »** (section 3.7) : le floor du jour et
  `floor_suspect`, une ligne seulement quand ils changent ;
- release `catalogue` (colonnes `ath`, `atl`, `ath_date`, `atl_date`).

### 3.1 Floor du jour (fichier « floor du jour », section 3.7)
- **Floor du jour = le floor tenu le plus longtemps dans la journée** de la
  fiche (en heures, de 00:00 à 24:00 UTC). On part du floor en vigueur à
  00:00, puis chaque changement du jour ; à durée égale, le plus récent.
  - Une annonce achetée dans la minute ne pèse qu'une minute : elle ne devient
    jamais le floor du jour.
  - Un jour sans changement garde le floor de la veille.
  - Le « jour » est le jour de la date de collecte, écrit dans le fichier.
- **Pas d'offre = case vide, jamais 0.** Si « pas d'offre » est ce qui a duré
  le plus longtemps, le floor du jour est vide.
- **Aucun floor avant la date de sortie** de la fiche (le prix boutique n'est
  pas un floor), **aucun après la date de collecte** du fichier.

### 3.2 Floor suspect (colonne `floor_suspect` du fichier « floor du jour », `oui` ou vide)
Un floor du jour est suspect s'il est :
- en dessous de **1 $** ;
- ou au-dessus de **15 000 $** ;
- ou à plus de **×20** (ou moins de **÷20**) de la **médiane des 30 jours
  précédents** de la même fiche.

S'il n'y a aucun jour dans les 30 jours précédents, seuls les deux premiers
critères (1 $ et 15 000 $) s'appliquent.

### 3.3 ATH / ATL (`catalogue`)
- **ATH / ATL = le plus haut / le plus bas des floors du jour valides.**
- Un floor du jour **non suspect** est valide.
- Un floor du jour **suspect** ne compte que s'il est le floor du jour **deux
  jours de suite** (cas des vrais graals). **Sous 1 $ ou au-dessus de
  15 000 $ : jamais**, même plusieurs jours de suite (v4, 28/11/2026 : des
  annonces « troll » à 160 000 $ ou 10¹⁵ $ restent en place des semaines).
  Conséquence voulue : une fiche dont le floor dépasse vraiment 15 000 $ a un
  `ath` plus bas que ce floor (le floor réel reste visible dans le fichier
  « floor du jour », marqué suspect).
- `ath_date` / `atl_date` = le jour de ce floor. Jamais après la date de
  collecte, jamais avant la date de sortie.
- **Valeur du tracker (my-nft-tracker) : quand on la garde.** Notre historique
  ne couvre pas tout. On garde l'ATH (ou l'ATL) du tracker, avec sa date,
  quand sa date tombe :
  - avant notre première donnée pour la fiche ;
  - dans le trou des comics du 30/09/2026 au 25/11/2026 (comics sans aucun
    relevé dans ce trou) ;
  - dans le futur, ou quand le catalogue n'a pas de date.
- **Une valeur du tracker gardée reste soumise aux seuils** : en dessous de
  1 $ ou au-dessus de 15 000 $, elle ne compte pas, et c'est notre valeur qui
  s'applique.
- **Période couverte par notre historique : notre valeur remplace celle du
  tracker.**
- Une fiche sans aucun floor du jour valide et sans valeur du tracker gardée
  a `ath`, `atl` et leurs dates **vides**.
- **Fiche pas encore sortie** (date de sortie après la date de collecte) :
  `ath`, `atl` et leurs dates **toujours vides**, même si le tracker y met le
  prix boutique (v4) ; ce prix reste visible dans `ath_brut` / `atl_brut`.
- **Fiche sans aucun relevé chez nous** : la valeur du tracker n'est gardée
  qu'entre 1 $ et 15 000 $, sinon la case est vide (v4).
- **Les valeurs brutes restent disponibles**, sans filtre : nouvelles
  colonnes `ath_brut`, `atl_brut`, `ath_brut_date`, `atl_brut_date`.

### 3.4 Ce que doivent faire les sites
- veveprice : **un jour suspect n'est pas tracé** sur les graphiques (un trou,
  pas un pic). Option : couper la courbe quand il manque plusieurs semaines.
- Les deux sites lisent `ath` / `atl` (filtrés) ; `ath_brut` / `atl_brut`
  servent au contrôle, pas à l'affichage.

### 3.5 Contrôles avant publication (Scrapeur)
- Aucun floor du jour à 0 ; aucune date future ; aucune date avant la sortie.
- `ath` ≥ `atl` quand les deux existent.
- Aucun `ath` ni `atl` sous 1 $ ou au-dessus de 15 000 $ (v4).
- Compte des changements par rapport à la version publiée (ATH, ATL, points
  de courbe retirés, jours marqués suspects), donné à Preda avant le go.

### 3.6 Compte final (mesuré le 27/11/2026)
Sonde scrapeur-veve run 46057442862 (commit be24fad), sur `prices-full` et `catalogue` de jetonveve du 27/11.
Par rapport au catalogue publié :
- **ATH change sur 4 909 fiches, ATL sur 3 440 ; l'un ou l'autre : 6 693.**
- Valeur du tracker gardée (hors période couverte, entre 1 $ et 15 000 $) :
  ATH 8 345 fiches, ATL 7 517 (la plupart ne changent pas).
- Dates seules (même valeur, autre jour) : ATH 3 001, ATL 5 188.
- Points de courbe marqués suspects : 107 990 jours sur 3 505 fiches.

### 3.7 Le fichier « floor du jour » (format décidé le 28/11/2026, RESEAU v3.38)
- **Où** : release `floors-jour` de `Leonessa2/jetonveve`, fichier
  `floors_jour.csv.gz`, plus `floors_jour.json` qui porte la date de collecte
  (`{"collecte": "AAAA-MM-JJTHH:MM:SSZ", "lignes": …, "sha256": …}`).
- **Colonnes** : `veve_uuid`, `date` (`AAAA-MM-JJ`, jour UTC), `floor`
  (point décimal, vide = pas d'offre ce jour-là), `floor_suspect` (`oui` ou
  vide).
- **Une ligne seulement quand le floor du jour ou `floor_suspect` change.**
  Un jour sans ligne garde la valeur de la ligne précédente de la même fiche,
  jusqu'à la date de collecte. Première ligne d'une fiche = son premier jour
  connu (jamais avant la date de sortie). Fichier trié par `veve_uuid` puis
  `date`.
- **Taille mesurée le 28/11/2026** (sonde scrapeur-veve run 46106667605,
  `prices-full` du 27/11, rien publié) : **1 668 081 lignes** pour 21 449
  fiches, **8,0 Mo** compressé, 88,9 Mo décompressé ; 10 233 lignes marquées
  suspectes. À comparer : `prices.csv.gz` = 2 451 107 lignes, 34,5 Mo
  compressé, 178 Mo décompressé. Lecture complète en Python : 2,2 s, 526 Mo
  de mémoire au plus.
- `prices-full` reste la source brute ; le fichier « floor du jour » est la
  source des courbes et des ATH/ATL.

### 3.8 Ordre de publication (RESEAU v3.38)
1. ✅ Correction n° 3 de veveprice en ligne (28/11) : case vide du nombre
   d'offres = « inconnu ».
2. Les trois corrections de veveprice en ligne : floor vide = pas de point
   (jamais 0 $) ; ATH/ATL vide = rien d'affiché (pas de repli sur le plus haut
   brut) ; garde-fou des floors douteux qui ne dépend plus du nombre d'offres
   (par exemple `floor_suspect`).
3. **Seulement ensuite** : le nombre d'offres vide (section 2), puis la règle
   des floors (fichier « floor du jour » et nouveaux ATH/ATL), sur go de Preda
   donné sur le compte de fiches qui changent, recompté juste avant.

## 4. Onglet `📝C-BLOG` — articles du blog VeVe, texte complet (accord de Preda, 27/11/2026, v3.34)

> Pour VeVe France (lot 6) et le module `blog` du bot. Mesuré le 27/11/2026
> par la sonde `sonde-blog.yml` (scrapeur-veve, run 46057600920), lecture
> seule.

**Où** : le Sheet du Scrapeur, onglet `📝C-BLOG`. Les autres projets le
**lisent seulement**. Ce n'est pas une release : c'est l'exception décidée
dans RESEAU.md pour les articles. Écrit par `blog.yml` (scrapeur-veve) une
fois par jour, vers 02:00 UTC prévu (GitHub peut retarder), plus l'étape
ECOMI du même fichier ; `medium-vers-blog.yml` a versé une fois l'archive
Medium.

**Une ligne = un article.** Lire les colonnes **par leur nom**, pas par leur
place : on peut en ajouter à la fin.

| Colonne | Ce que c'est | Garantie |
|---|---|---|
| `url` | **Adresse d'origine** de l'article | Écrite à la première collecte et **jamais changée** ensuite, même si VeVe déplace l'article (depuis le commit 6093709). Une seule ligne par adresse (0 doublon le 27/11). **C'est la clé à utiliser par VeVe France.** |
| `date` | Date de parution | Lue avec la lecture normale du Sheet, elle arrive en **`JJ/MM/AAAA`** (ex. `25/11/2026`). Pour 62 articles réimportés par VeVe le 03/03/2024, c'est la vraie date reprise de l'archive Medium. Jamais vide. |
| `title` | Titre | VeVe peut le changer : **ce n'est jamais une clé.** |
| `content` | **Texte complet**, sans mise en forme (paragraphes séparés par des sauts de ligne, sans images) | Récupéré une fois : un article déjà récupéré n'est **pas relu**, même si VeVe le modifie. Coupé à 45 000 caractères au plus (aucun article ne l’atteint le 27/11 ; le plus court fait 461 caractères, la médiane 4 020). Jamais vide. |
| `category` | Rubrique | Rubriques de veve.me (`Artworks`, `Collectibles`, `Comics`, `Events`, `Fandoms`, `MCP`, `News`, `Updates`, `VeVe`, `VeVe 101`), `Medium` (ancienne archive, arrêtée en avril 2023), `ECOMI` (blog du jeton OMI). Jamais vide. |
| `first_seen` / `last_seen` | Date de collecte (première / dernière), UTC, `AAAA-MM-JJ HH:MM:SS` | Chaque ligne porte ainsi sa date de collecte. |
| `slug`, `tags`, `author`, `reading_time`, `excerpt`, `image_url` | Compléments | `slug` est la clé interne du Scrapeur (préfixe `medium-` ou `ecomi-` selon la source). |

**Autres garanties** : une ligne n'est **jamais effacée** (une panne de la
source laisse l'onglet tel quel) ; un nouvel article de veve.me apparaît au
plus tard au passage du lendemain.

**Contenu le 27/11/2026** : 1 617 articles (veve.me 1 133, Medium 471, ECOMI
13). Aucun champ vide parmi `url`, `date`, `title`, `content`, `category`.

**⚠️ Doublons, pour VeVe France** :
- Le même article peut exister **deux fois** dans l'onglet : sur veve.me
  (réimport) et dans l'archive Medium, avec deux adresses différentes et un
  texte identique ou presque (environ 69 paires connues ; 2 lignes ont un texte
  strictement identique à une autre).
- D'après Preda, la plupart des articles sont **déjà adaptés** sur
  vevefrance.fr, souvent **sous un autre titre**. Pour repérer un article déjà
  adapté, **comparer le texte (`content`)**, pas le titre.

## 5. Bannières VeVe (v2, décision de Preda du 28/11/2026)

> Décor pour les sites (VeVe France d'abord), **sans suivi** : pas
> d'historique, pas de dates de début et de fin.

**Où** : release `bannieres` de `Leonessa2/jetonveve`, deux fichiers :
- `bannieres.csv` : **seulement les bannières affichées sur l'accueil de
  www.veve.me au moment de la collecte**. Le fichier est **remplacé** à chaque
  collecte.
- `bannieres.json` : `{"collecte": "AAAA-MM-JJTHH:MM:SSZ", "lignes": …,
  "sha256": …, "source": "https://www.veve.me/"}` (date de collecte en UTC ;
  `sha256` = empreinte de `bannieres.csv`).

**Quand** : une lecture par jour (`bannieres.yml` de jetonveve, prévu à 06:41
UTC ; GitHub peut retarder).

| Colonne | Contenu |
|---|---|
| `position` | Place dans le carrousel de VeVe, nombre entier ; afficher par ordre croissant. Les numéros peuvent sauter (le 28/11 : 1, 3, 4, 5, 6, 9, 10). |
| `image_ordinateur` | Adresse complète (`https://…`) de l'image pour ordinateur |
| `image_mobile` | Adresse complète (`https://…`) de l'image pour mobile |
| `lien` | Adresse complète (`https://…`) où mène la bannière ; peut être vide |

**Règles**
- Si la page est illisible ou n'a aucune bannière, **rien n'est publié** : la
  release garde la liste d'avant, et le filet de jetonveve donne l'alerte.
- Quand VeVe n'affiche que sa bannière « de secours », c'est elle qui est
  dans la liste.
- Les images s'affichent directement depuis l'adresse de VeVe (vérifié : ça
  fonctionne), sans les stocker. Le texte des bannières est dans l'image, en
  anglais.

**Première collecte** : 28/11/2026 à 05:30 UTC (jetonveve run 46112401590),
**7 bannières**.

