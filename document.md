RAPPORT DE :
STAGE D’INITIATION
Elaboré par : khachroumi Amal
Encadré par : Monsieur Ben Mohammed Ahmed
Société d’accueil : Tunisie Telecom
Année Universitaire : 2019/2020

Remerciements
J’ai l’honneur d’exprimer mes salutations et mes remerciements à tous le personnel de
TUNISIE TELECOM (centre technique IT KASBHA) et plus précisément mon
encadreur Monsieur Ben Mohamed Ahmed, Chef Subdivision Administration systèmes
et bases de données pour sa confiance, ses précieuses suggestions, ses compétences, ses
disponibilités, ses conseils précieux, et son soutien considérable tout au long de mon
stage.
Un grand merci pour tous ce qu’il m’a appris.
Je tiens aussi à remercier Madame Yosra et Aida Pour l’aide qui m’a porté dans le
département technique El-Kasbah, afin que je trouve les meilleures conditions durant
mon stage.
P age 2 | 40

Table des matières
Table of Contents
Introduction générale . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .6
Chapitre 1 : Présentation de l'entreprise………………………………………………………………….7
1. Présentation générale de l’entreprise d'aceuil Tunisie Telecom……………………………………….7
2. Organigramme de Tunisie Telecom (TT) ……………………………………………………………..8
3. La direction centrale des systèmes d'information (DCSI)…………………………………………….8
3.1.service réseau informatique…………………………………………………………………………..9
3.2.service sécurité informatique………………………………………………………………………..9
3.3.service administration système……………………………………………………………………...11
Chapitre 2 : Partie théorique …………………………………………………………………………...12
1. Rôle d'administrateur de base de données……………………………………………………………12
2. Les types de systèmes de bases de données………………………………………………………….13
2.1. Les bases de données hiérarchiques………………………………………………………………..13
2.2. Les bases de données réseau……………………………………………………………………….13
2.3. Les bases de données relationnelles………………………………………………………………..13
2.4. Les bases de données objet………………………………………………………………………...13
3. Historique de l'Oracle………………………………………………………………………………..14
4. Les versions de l'oracle………………………………………………………………………………14
5. Architecture de l'Oracle………………………………………………………………………………15
5.1. La base de données Oracle…………………………………………………………………………16
5.2. Instance Oracle……………………………………………………………………………………..17
5.2.1.Des processus d’arrière plan……………………………………………………………………...17
5.2.2. Des structures mémoires…………………………………………………………………………18
6. Back_up Oracle :sauvegarde et restauration…………………………………………………………19
6.1. Les fonctions de RMAN…………………………………………………………………………...19
6.2. Principe de stockage des sauvegardes……………………………………………………………...19
Chapitre 3 :Partie pratique ……………………………………………………………………………...20
A-Motivation……………………………………………………………………………………………20
1. Le principe de la virtualisation……………………………………………………………………….20
2. Les outils de virtualisation…………………………………………………………………………...20
P age 3 | 40

2.1. Oracle Virtual Machine…………………………………………………………………………….20
2.2. Vmware…………………………………………………………………………………………….21
3. Les systèmes d'exploitation(SE) à base Linux……………………………………………………….21
3.1. Oracle Linux……………………………………………………………………………………….21
3.2 Ubuntu………………………………………………………………………………………………21
4. Base de données Oracle 11g………………………………………………………………………….21
B-Réalisation de la partie pratique……………………………………………………………………...22
1. Installation de Vmware………………………………………………………………………………22
2. Installation de Oracle Linux 6 sous Vmware………………………………………………………...23
3. Installation de Ubuntu sous Vmware………………………………………………………………...25
4. Installation d' Oracle 11g sur Ubuntu………………………………………………………………...27
4.1. Préparation de l’OS pour installer Oracle: Préinstallation…………………………………………27
4.2. Installation d'Oracle 11g…………………………………………………………………………...31
5. Création d'une base de données simple………………………………………………………………36
Conclusion……………………………………………………………………………………………...40
P age 4 | 40

Liste des figures
Figure 1: Organigramme administratif de Tunisie Télécom……….. 8
Figure 2: Présentation de DCSI……………………………………. 9
Figure 3: Data Center………………………………………………. 10
Figure 4: Firewall…………………………………………………….. 11
Figure 5: Architecture de l'Oracle……………………………………. 15
Figure 6: stockage……………………………………………………. 19
Figure 7:Début d'installation Setup…………………………………... 22
Figure 8: Vmware Workstation……………………………………….. 23
Figure 9: Début d'installation et personnalisation Linux…………….. 24
Figure 11:Début d'installation………………………………………… 26
Figure 12:Gestion mémoire…………………………………………… 26
Figure 13: Oracle Linux 6…………………………………………….. 26
Figure 14: Obtention de l'adresse IP…………………………………. 27
Figure 15: script pour modifier le nom.................................................. 28
Figure 16: Installation des packages………………………………….. 28
Figure 17: Configuration du mot de passe du compte………………… 29
Figure 18: copie des deux fichiers sous /oracle répertoire…………….. 29
Figure 19: session Xming activée……………………………………… 30
Figure 20: Début d'installation .............................................................. 31
Figure 21: Setup Xming………………………………………………... 32
Figure 22: Les étapes de configuration………………………………... 33
Figure 23: éditer le script .bash_profile………………………………. 34
Figure 24: Configuration du Listener..................................................... 35
Figure 25: Configuration réseau………………………………………. 35
Figure 26: le Listener est configuré........................................................ 36
Figure 27: Début de la configuration de la base……………………… 37
Figure 28: Modèle BD généraliste ou traitement transactionnel……. 38
Figure 29: Confirmation de la Base de données est terminée……… 39
P age 5 | 40

Introduction générale
Étant actuellement étudiante à Sup'com, et pour avoir une formation complète en tant
qu'ingénieure, je dois effectuer un stage d’initiation.
L'objectif pédagogique de ce stage est de me faire découvrir la vie
professionnelle, le monde de l’entreprise et l'environnement humanitaire. De ce fait, ce
rapport est un document représentatif de mon stage d’initiation que je l’ai effectué au
sein de la division administration systèmes et bases de données qui se trouve à la
Centrale IT de la Kasbah, durant la période allant de 22/07/2019 jusqu’à 24/08/2019.
Les bases de données ont pris une place importante en informatique, et en
particulièrement dans le domaine de la gestion. Actuellement elles sont au cœur des
entreprises. Durant Ce stage je profite donc ,d’améliorer mes connaissances théorique
sur le SGBDs ainsi que ses fonctionnalité, ses architectures.
Dans ce rapport, je vais présenter dans le premier chapitre une présentation
générale de TUNISIE TELECOM dans son environnement en appuyant sur ses
principales activités. Dans le deuxième chapitre je vais parler de la partie théorique de
stage, finalement, dans le troisième chapitre je vais présenter la partie pratique.
Le rapport se termine par une conclusion qui résume l’ensemble de nos travaux ainsi des
perspectives.
P age 6 | 40

Chapitre 1 : Présentation de l'entreprise
1. Présentation générale de l’entreprise d'aceuil Tunisie Telecom:
L’office National de Télécom est un établissement public à caractère commercial. Il a été
crée le 17/04/1995 par la chambre des députés par la loi N°95-36. Cet Office National de
Télécom est né le 01/01/1996 connu par son nom commercial Tunisie Télécom.
Elle se compose de 24 directions régionales, de 140 Espaces TT et points de vente et de
plus de 13 mille points de vente privés.
Elle emploie plus de 6000 agents.
Tunisie Télécom a ainsi pour mission d’assurer les activités relatives au domaine de
télécommunication. Il est notamment chargé de :
- L’installation, le développement, l’entretien et l’exploitation des réseaux de
téléphone et la transmission des données.
- La promotion des nouveaux services de télécommunication.
- L’offre de tous les services publics ou privés de télécommunication correspond
aux divers besoins à caractère social et économique.
- La participation à l’effort national d’enseignements supérieur au niveau du secteur
de télécommunication.
- La promotion de la coopération dans tous les domaines de télécommunications,
l’Office National de Télécommunications Tunisie Télécom est placé sous la tutelle
du ministère de la communication ; son siége est fixé à Tunis.
P age 7 | 40

2. Organigramme de Tunisie Telecom (TT) :
Figure 1: Organigramme administratif de Tunisie Télécom
3. La direction centrale des systèmes d'information (DCSI):
Cette direction s’occupe de la mise en œuvre de l'infrastructure informatique et des
réseaux sécurités entreprise (Data center) ainsi que l'administration des systèmes et les
bases de données .
P age 8 | 40

Direction Centrale des systeme d'informatique
Direction des operation TI

| Centre de  | Centre de gestion  | Administration  |
| ---------- | ------------------ | --------------- |
Centre TI
| factoration | client et resource | et supervision |
| ----------- | ------------------ | -------------- |
gestion de
Centre
|     | resource  | Administration  |
| --- | --------- | --------------- |
Serveurs et OS
d'impression BD
operation
Gestion de la  Stockage
|     | gestion client  | Centre de  |
| --- | --------------- | ---------- |
factoration  Sauvegarde
|     | et serveur | supervision |
| --- | ---------- | ----------- |
Archivage
client
| Gestion de  |     | Gestion de  |
| ----------- | --- | ----------- |
Securite
| recouvrement |     | deploiement |
| ------------ | --- | ----------- |
gestion de la
Reseaux
mediation
Figure 2: Présentation de DCSI
Elle comprend des différents services :
         3.1.service réseau informatique :
Ce service  a en charge l'ensemble des réseaux de télécommunications de l'entreprise,
qui couvrent les réseaux locaux et distants : téléphonie, internet, intranet...
Il est responsable des bonnes performances du réseau, organise et définit les procédures
d'interconnexion des équipements qui constituent le réseau informatique :
routeurs,commutateurs(switch),etc...
        3.2.service sécurité informatique :
Ce service vise principalement les objectifs suivants :
P age  9 | 40

➢ Confidentialité: seules les personnes autorisées peuvent avoir accès aux
informations qui leur sont destinées (notions de droits ou permissions) à travers la
protection des ports. Tout accès indésirable doit être empêché.
➢ Authentification: les utilisateurs doivent prouver leur identité par l'usage de code
d'accès.
➢ sécurité des données : Les données mises en place sur les serveurs de centre Data
doivent être accessible à tout moment et protégées des dégâts extérieurs. Il y a
ainsi des protections contre les coupures électriques, les risques d'incendie, l'accès
de personnes malveillantes sur les serveurs ...
Figure 3: Data Center
Il existe plusieurs méthodes pour protéger un réseau informatique , le plus connu logiciel
est le pare-feu (Firewall) qui sert à surveiller et contrôler les applications et les flux des
données.
P age 10 | 40

Figure 4: Firewall
3.3.service administration système:
Ce service est responsable de la disponibilité des informations au sein de l'entreprise et
la veille technologique dans le périmètre technique des matériels et logiciels de type
serveur, principalement l’installation, désinstallation ,la maintenance et la supervision
des systèmes d'exploitation :Red Hat , Ubuntu ,Windows-server, CentOS..
L’une des missions les plus importantes d'un administrateur système consiste à veiller
à la sécurité et à la sauvegarde des données sur le réseau complet. En cas de panne ou
d’incident, il doit se montrer réactif et effectuer les réparations nécessaires dans les plus
brefs délais. Son travail ne s’arrête pas là: grâce à une veille technologique permanente,
l’administrateur systèmes et réseaux cherche à optimiser le système en testant de
nouveaux matériels.
P age 11 | 40

Chapitre 2 : Partie théorique
1. Rôle d'administrateur de base de données :
L’ Administrateur de Bases de Données intervient dans la conception, l’administration et
la maintenance des bases de données, ainsi que dans l’assistance aux informaticiens et
aux utilisateurs. L’ Administrateur de Bases de Données a ainsi pour misions principales
de :
• Prévoir les volumes de données dans l’optique de choisir les outils servant à
construire et à exploiter la base
• Concevoir, tester et mettre en place des progiciels SGBD (système de
gestion de base de données)
• Préconiser des bonnes pratiques à usage des équipes de développement
• Concevoir et définir les paramètres des bases de données
• Réfléchir et mettre en place le dimensionnement du serveur
• Organiser les systèmes de gestion de bases de données tout en tenant
compte des paramètres de cohérence, qualité et sécurité
• Mettre en place des normes qualité et élaborer des tableaux de bord pour en
assurer le suivi
• Veiller à la disponibilité des informations et à leur facile utilisation
• Assister les développeurs et les techniciens d’exploitation dans l’exercice
de leur fonction
• Assurer une veille technologique et un contrôle de la ou des bases de
données.
P age 12 | 40

2. Les types de systèmes de bases de données :
2.1. Les bases de données hiérarchiques
Les tous premiers programmes de bases de données permettaient de structurer
l’information de façon hiérarchique: chaque enregistrement dépendait d’un seul
enregistrement. Présenté sous forme d’arbre avec ses ramifications.
2.2. Les bases de données réseau:
les bases de données réseau prennent le relais de façon très satisfaisante. En permettant
les relations n-n (plusieurs parents / plusieurs enfants).D’une structure en arbre, les bases
de données deviennent des graphes.
2.3. Les bases de données relationnelles:
C’est le type de bases que l’on connaît et que l’on pratique aujourd’hui. Basé sur
l’algèbre relationnel et les travaux de E.F. Codd, il permet de modéliser facilement et
sans grosse contraintes les systèmes du monde réel et de créer des bases de données
simples à maintenir, à faire évoluer et indépendantes de leur support.
Dans ce type de bases de données, les données sont organisées entables.
2.4. Les bases de données objet:
La grande idée est ici de permettre «d’attaquer» la base de donnée de façon transparente
via ses «objets». Les objets sont un concept de programmation qui simplifie la création
de logiciel et apporte de nombreux atouts aux projets informatiques importants.
Data Base Management System (DBMS) : Oracle, MySQL,Microsoft SQL
Server,PostgreSQL,DB2,Microsoft Access,SQLite...
P age 13 | 40

3. Historique de l'Oracle:
Software Development Laboratories a été créé en 1977. En1979, l'entreprise change de
nom en devenant Relational Software, Inc. (RSI) et introduit son produit Oracle V2
comme base de données relationnelle. La version 2 ne supportait pas les transactions
mais implémentait les fonctionnalités SQL basiques de requête et jointure. Il n'y a
jamais eu de version 1, pour des raisons de marketing, la première version a été la
version 2. Celle-ci fonctionnait uniquement sur les systèmes Digital VAX/VMS.
4. Les versions de l'oracle :
- En 1984, la version 4 supporte la cohérance en lecture (read consistency).
- En 1985, la version 5 supporte les requêtes distribuées, dans le cadre de l'intégration du
modèle client-serveur avec l'arrivée des réseaux au milieu des années 1980.
- En 1988, la version 6 supporte le PL/SQL, le verrouillage de lignes (rowlevel
locking) et les sauvegardes à chaud (hot backups, lorsque la base de données est
ouverte). Oracle met sur le marché son ERP Oracle Financials basé sur la base de
données relationnelle Oracle Database.
- En 1992, la version 7 supporte les contraintes d'intégrité, les procédures stockées et les
déclencheurs (triggers).
- En 1995, acquisition d'un puissant moteur multidimensionnel, commercialisé sous le
nom d'Oracle Express.
- En 1997, la version 8 introduit le développement orienté objet, et les applications
multimédia grâce aux services Oracle interMedia2, renommé Oracle Multimedia depuis
la version 11g3.
- En 1999, la version 8i d'Oracle est publiée dans le but d'affiner ses applications avec
Internet (le i fait référence à Internet). La base de données comporte nativement une
machine virtuelle Java.
- En 2001, la version 9i ajoute 400 nouvelles fonctionnalités et permet de lire et d'écrire
des documents XML. Elle intègre le moteur OLAP: le moteur Oracle Express est
dorénavant référencé au sein de l'option Oracle OLAP.
P age 14 | 40

Les données multidimensionnelles sont accessibles à partir du langage SQL.
- En 2003, la version 10g supporte les expressions rationnelles. Le g signifie grid ; un
des atouts marketing de la 10g est en effet qu'elle supporte le grid computing.
- En novembre 2005, la version 10g Express Edition, complètement gratuite, est publiée,
ainsi que la version 10g Release 2.
- En juillet 2007, la version 11g Linux et Windows.
- En septembre 2009, la version 11g Release 2 est publiée4.
- En juillet 2013, la version 12c est publiée5.
5. Architecture de l'Oracle:
Figure 5: Architecture de l'Oracle
P age 15 | 40

Un serveur Oracle est un système qui permet de gérer les bases de données et qui offre
un moyen de gestion des informations ouvert, complet et intégré.
Un serveur Oracle est constitué d’une instance et d’une base de données.
5.1. La base de données Oracle :
Une base de données complète est constitué d'un certain nombre de fichiers :
• Des fichiers de données (datafiles ou databasefiles) :
les fichiers de données sont pour stocker les données (essentiellement les tables et leurs
lignes), mais aussi les autres objets oracle connexes aux tables : (index, vues,
synonymes, database links, procédures stockées, etc.)
• Des fichiers journaux (logfiles ou redologfiles):
Les fichiers journaux servent à mémoriser toutes les modifications (validées ou non)
faites sur la base, à des fins de reprise en cas de perte de données physiques.
La journalisation (assurée par le process LGWR) est un mécanisme permanent et
obligatoire d'Oracle, pour assurer un minimum de sécurité des données.
• Des fichiers de contrôle (control files):
un fichier de contrôle qui spécifie le nom et l’emplacement des fichiers, le nom de la
base.
• Un fichier d'initialisation ou de paramétrage (init file)
• Des fichiers d’archivage (optionnel) pour archiver les fichiers de contrôle
• Un fichier de paramètres (optionnel) qui stocke tous les paramètres de la
base
• Des fichiers de trace pour répertorier toutes les tâches et erreurs effectuées
et optionnellement
• Un fichier de mot de passe (password file)
• et des fichiers d'archivage des journaux
P age 16 | 40

Les fichiers de données initiaux, les fichiers journaux et les fichiers de contrôle sont
créés par l'ordre SQL 'CREATE DATABASE'
5.2. Instance Oracle:
L’instance Oracle est constituée par :
5.2.1.Des processus d’arrière plan :
Ils gèrent et appliquent les relations entre les structures physiques et les structures
mémoires. Ces processus représentent le programme qui rentre directement en
interaction avec le serveur Oracle.Ils répondent à toutes les demandes et renvoient les
résultats.
Il en existe deux catégories :
+ les processus d’arrière plan obligatoires :
*DBWR (Data Base Writer) :écrit le contenu du cache de données dans les fichiers de
données de façon périodique en mettant à jour le point de restauration sur les fichiers
log .
*LGWR (Log Writer) :écrit le contenu du cache de reprise dans les fichiers de log
toutes les trois secondes ,quand le cache de reprise est plein au tiers et quand un
processus DBWR décharge des données modifiées .
*CKPT (Chekpoint) :Pour assurer la synchronisation et la cohérence des données.
*SMON (System Monitor) :
-Effectue la restauration lors de reprise après panne
-Nettoie les segments temporaires
-Fusionne certains extents libres contigue PMON (Process Monitor) pour gérer les
pannes des processus clients .
*PMON (Process Monitor) :Pour gérer les pannes des processus clients
+les processus d’arrière plan facultatifs : ARCn, LMDn, RECO, CJQ0, LMON, Snnn,
Dnnn, Pnnn, LCKn, QMNn
NB: L'archivage des redo log files :
Ce processus (process ARCH ou "ARCHIVER") est optionnel et permet de faire des
restaurations les plus à jour possible.
P age 17 | 40

En l'absence d'archivage, on ne pourra récupérer les données que de la dernière
sauvegarde. Avec l'archivage on récupérera ces mêmes données + les modifications
qui ont été faites entre la sauvegarde et le crash. (seules les transactions en cours au
moment du crash sont perdues).L'archivage permet de garder tout l'historique des
fichiers redologs, qui sont recopier sur le répertoire d'archivage dès qu'ils sont pleins
(Switch).
Si on n'archive pas les redologs sont écrasés cycliquement, puisque rappelons le, ils
sont utilisés de manière séquentielle et circulaire !
Il est possible d'autoriser l'archivage automatique de manière dynamique par la
commande suivante :
SQL> ALTER SYSTEM ARCHIVE LOG START;
5.2.2. Des structures mémoires :
Elles se composent essentiellement de deux zones mémoires :
-La zone mémoire allouée à la SGA(System Globel Area) :
Elle est allouée au démarrage de l’instance et qui représente une composante
fondamentale d’une instance Oracle.Son but est d'économiser les E/S.
Elle contient:
+la zone mémoire partagée par tous les utilisateurs de la base de données
+le cache de tampons de la base de données (Data Base Buffer cache).
+le tampon de journalisation(redo log Buffer) log des changements récents .
-La zone mémoire allouée à la PGA (Program Global Area) :
Elle est allouée au démarrage du processus serveur. Elle est réservée à chaque
processus utilisateur qui se connecte à la base de données Oracle et libérée à la fin du
processus.
P age 18 | 40

6. Back_up Oracle :sauvegarde et restauration:
La commande RMAN (Recovery MANager ) permet aux DBA de gérer les opérations
de sauvegarde/restauration de manière souple et optimisée.
6.1. Les fonctions de RMAN:
RMAN offre la possibilitée de :
• réaliser des sauvegardes globales de la base, d'espaces disque logiques
(tablespace), de fichiers de données (datafiles), de fichiers de contrôle
(controlfiles) et de fichiers d'archive (archivelog).
• éviter de sauvegarder les blocs Oracle vides, ce qui permet un gain significatif de
volume de sauvegarde.
• gérer les périodes de conservation des sauvegardes.
• dupliquer une base de données de manière simple.
• éditer des rapports.
6.2. Principe de stockage des sauvegardes:
Figure 6: stockage
BackupPiece: C'est une entité physique contenant 1 ou plusieurs fichiers de données.
Un fichier peut très bien être sur plusieurs backup pieces. Leur nombre et leur taille
dépendent du paramètre maxpiecesize.
BackupSet: C'est une entité logique contenant un ou plusieurs backup pieces .
P age 19 | 40

Chapitre 3 :Partie pratique
Dans cette partie , on commence à découvrir un peu le rôle d'un admistrateur système et
aussi bien le rôle d'un administrateur de base de donnée, à travers des différentes
fonctionnalités.
But:
-Installation des systèmes d'exploitation Oracle Linux et Ubuntu sous Vmware virtual
Machine .
-Installation du Oracle 11g sur Ubuntu .
-Création d'une base de données simple .
A-Motivation:
1. Le principe de la virtualisation :
La virtualisation est l'ensemble des technologies matérielles et/ou logicielles qui
permettent de faire fonctionner plusieurs systèmes d'exploitation et/ou plusieurs
applications sur une même machine, séparément les uns des autres, comme s'ils
fonctionnaient sur des machines physiques distinctes. Il existe beaucoup d'intêtrets , par
exemple:
-Migrer facilement d'une machine virtuelle à une autre .
-Economiser de l'argent sur le matériel .
-Développer ou tester des logiciels avec possibilité de recommencer sans casser le
système hôte ,etc...
2. Les outils de virtualisation:
2.1. Oracle Virtual Machine: Oracle VM est le serveur de virtualisation de
l'entreprise Oracle fondée en 1977.OVM est un logiciel libre et gratuit qui permet
l'exploitation d'une machine serveur virtuelle.
P age 20 | 40

2.2. Vmware: La société Vmware INC, fondée en 1998, propose plusieurs produits
liés à la virtualisation d'architectures x86.
Dans la suite de pratique , on va utiliser Vmware Server pour ses nombreux
advantages ,parmi lesquelles on cite:
Vmware permet de virtualiser n’importe quelle OS, il permet de virtualiser plusieurs
système d’exploitation sans faire de multiboot et avoir une seule configuration machine.
Il permet aussi de configurer la quantité de mémoire, l’espace disque dur et l’accès ou
pas au USB, réseau, carte son, etc…
3. Les systèmes d'exploitation(SE) à base Linux:
3.1. Oracle Linux: est un système d’exploitation Open Source Linux. Il convient
tant à des applications Oracle qu’à une utilisation générale. Il est compatible avec Red
Hat Enterprise Linux.
À part le fait que le téléchargement d'Oracle linux est gratuit, ce dernier représente un
système éprouvé et optimisé : Oracle investit énormément sur ce système. En interne, il
est testé pas moins de 128 000 heures par jour.
3.2 Ubuntu: est un système d'exploitation GNU/Linux basé sur la distribution
Linux (ensemble cohérent de logiciels libres assemblés autour du noyau Linux).
Ubuntu se définit comme un système d'exploitation utilisé par des millions de PC en
représentant une interface simple , intuitive et sécurisée.
On trouve aussi d'autres SE à base Linux comme Fedora,CentOS,RedHat,etc...
4. Base de données Oracle 11g:
Oracle Database 11g est adapté aux environnements transactionnels et décisionnels
sophistiqués. Non seulement ce SGBD améliore nettement les performances de 10g mais
aussi, et surtout, il offre des avantages tels qu'une installation simple et rapide, et des
fonctions complètes d'auto-gestion .
P age 21 | 40

B-Réalisation de la partie pratique:
1. Installation de Vmware:
les étapes d'installation en gros :
-télécharger l'application VMware-workstation-full-14.0.0-6661328
Figure 7:Début d'installation Setup
P age 22 | 40

Figure 8: Vmware Workstation
2. Installation de Ubuntu sous Vmware:
Les étapes d'installation en gros :
-télécharger d'abord le fichier image ubuntu-18.10-desktop-amd6
P age 23 | 40

Figure 9: Début d'installation et personnalisation Linux
P age 24 | 40

Figure 10: Ubuntu 18.04
3. Installation de Oracle Linux 6 sous Vmware:
Les étapes d'installation en gros :
-télécharger d'abord le fichier image OracleLinux-R6-U3-Server-x86_64-dvd
P age 25 | 40

Figure 11:Début d'installation Figure 12:Gestion mémoire
Figure 13: Oracle Linux 6
P age 26 | 40

4. Installation d' Oracle 11g sur Oracle Linux 6:
Cette section contient des instructions étape-par-étape ,détaillée , pour
l'installation d'Oracle 11g .
4.1. Préparation de l’OS pour installer Oracle: Préinstallation :
-se connecter d'abord en tant que root.
-télécharger file1.zip et file2.zip liés à l'installation.
-Obtenir l'adresse IP à partir de la commande ifconfig -a , dans ce cas , ma adresse est
192.168.2.133
Figure 14: Obtention de l'adresse IP
P age 27 | 40

-Changer le nom de la machine : localhost par oracle :
Figure 15: script pour modifier le nom
-lancer l’installation des packages par la commande: yum install oracle-rdbms-server-
11gR2-preinstall
Figure 16: Installation des packages
-Suite à la dernière commande, un compte ORACLE est créé. Il faut juste Changer le
mot de passe du ce compte.
P age 28 | 40

-
Figure 17: Configuration du mot de passe du compte
-créer un sous répertoire soft sous /oracle en saisissant les commandes suivantes:
mkdir /oracle
chown oracle:oinstall /oracle
mkdir /oracle/soft
chmod a+w soft (pour permettre à tous les utilisateurs le droit d'écrire).
-installer Filezilla (FileZilla_3.32.0_win64-setup.exe ) pour copier sous /oracle/soft les
deux fichiers .zip du windows vers la machine virtuelle à partir de la connection par
l'adresse IP du hôte .
Figure 18: copie des deux fichiers sous /oracle répertoire
P age 29 | 40

- lancer l'extraction du contenu de chaque fichier . Zip par la commande :
unzip p13390677_112040_Linux-x86-64_1of7.zip
unzip p13390677_112040_Linux-x86-64_2of7.zip
- Une fois l’extraction achevée, supprimer les fichiers zip par :rm *.zip ( il faut garde le
repertoire database)
-Installer Xming-6-9-0-31-setup.exe ( pour le graphique) puis lancer une session avec
putty en activant X11:
Figure 19: session Xming activée
-se placer sous le répertoire database , se connecter en tant que oracle et lancer
l'installation par ./runInstaller
P age 30 | 40

Figure 20: Début d'installation
4.2. Installation d'Oracle 11g:
-installer Xming-6-9-0-31-setup.exe puis lancer Xming pour le graphique :
P age 31 | 40

Figure 21: Setup Xming
-lancer l'insatallation par . /runInstaller
- suivre les étapes de configuration:
P age 32 | 40

Figure 22: Les étapes de configuration
P age 33 | 40

-exécution de la commande : vi .bash_profile
Figure 23: éditer le script .bash_profile
-exécuter le script par . .bash_profile
-Avec une session de Xming ou X11 est lancé en Putty , lancer l'install de Listener
par : netca (configuration des services Oracle Net)
P age 34 | 40

Figure 24: Configuration du Listener
-lancer les commandes :
export ORACLE_HOME=/oracle/app/product/11.2.0./dbhome_1
netmgr (oracle net manager)
-
Figure 25: Configuration réseau
P age 35 | 40

-vérifier le statut du Listener par la commande :lsnrctl status
Figure 26: le Listener est configuré
L'installation se termine avec succès.
5. Création d'une base de données simple:
- créer la base de données en utilisant l'assistant "DBCA"(Assistant de Configuration de
Base de Données) .
-avec une session Xming autorisée, on lance l'assitant de configuration de Base de
Données (DBCA)
-Pour le premier écran on trouve les types d’opération suivants :
➢ Créer une base de données : a pour but de stocker les Informations de production
correspondant à une application.
➢ Configurer les options de base de données : Plusieurs options de configuration
sont définies au niveau de la base de données. Trois onglets de gestion clés
contiennent ces options : Maintenance, Limites et Paramètres du client.
P age 36 | 40

 Supprimer une base de données : On peut aussi utiliser (DBCA, Data base
Configuration Assistant), qui permet la suppression d'une base.
 Gérer les modèles : L’assistant permet de définir, créer, modifier et supprimer
des modèles de base de données personnalisée.
on coche évidemment "Créer une base de données".
Figure 27: Début de la configuration de la base
-Pour le deuxième écran , on trouve le choix du modèle de la base de données.
P age 37 | 40

Figure 28: Modèle BD généraliste ou traitement transactionnel
-suivre les étapes de configurations :
P age 38 | 40

Figure 29: Confirmation de la Base de données est terminée
P age 39 | 40

Conclusion
Ce rapport est le résultat des travaux réalisés au cours de la période que j’ai
passé à l’espace commercial de Tunisie Télécom de Kasbah, tout en effectuant les
différentes applications informatiques et les différentes tâches réalisées par les
personnels de ce centre. Ce stage m’a été d’une grande utilité pour plusieurs raisons En
effet, il m’a permis d’améliorer mes connaissances, de suivre de prés le fonctionnement
des différentes activités des télécommunications et de m’intégrer dans le milieu
professionnel. Finalement, j'espère que mon travail serait à la hauteur en souhaitant
que j’atteigne la cible visée par ce rapport.
P age 40 | 40