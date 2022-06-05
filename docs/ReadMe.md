<a href="ReadMe.en.md"><img src="images/en.svg" valign="top" align="right"/></a>
<a href="ReadMe.md"><img src="images/de.svg" valign="top" align="right"/></a>
[![Version][version-badge]][version-url]
[![License][license-badge]][license-url]
<!--
[![Bugs][bugs-badge]][bugs-url]
-->

[![Logo][logo]][project-url]

### Live Long And Prosper

Hier kommst sie - die nächste Entwicklungstufe der 
Hausautomation. Sie basiert auf Home Assistent, dem zurecht beliebten zentralen
Steuerungssystem in einem Smart Home oder Smart House. Wie Home Assistent ist 
sie ebenfalls als kostenlose und quelloffene Software konzipiert, die in den 
wesentlichen Teilen in Python entwickelt wird und deren Hauptaugenmerk auf 
lokaler Steuerung und Privatspäre liegt. Da ich mich allerdings in der C / 
C++ / C# - Entwicklung mehr zuhause fühle, werden viele unterstützende 
Bibliotheken eher in C++ entwickelt werden. Aus dem gleichen Grund werde ich auch
das eher auf einer "Modulhierarchie" bestehende Grundgerüst auf eine Klassenhierarchie
umstellen (so gut es Python eben zulässt), wo jedem, der sich mit 
Klassenhierarchien etwas auskennt aber auch "Einsteigern", relativ schnell klar
wird, welche Klasse welche Aufgaben übernimmt, welche Teile der "Schnittstelle" 
von allen benutzt werden dürfen und welche Teile nur innerhab der Klasse für die 
Implementierung der Funktionalität vorhanden sind und eben **NICHT** von allen 
aufgerufen werden dürfen. Leider unterstützt Python die Verwendung von 
(Achtung, C++ - Code) ```private``` oder ```protected``` in Klassen nicht,
so das ich "nur" darauf vertrauen kann, das die nicht öffentlichen Teile der 
Implementierung, von denen, die dieses Projekt für sinnvoll und interessant
halten, als nicht öffentliche Teile der Implementierung respektiert werden.
Wie heißt es doch im Handwerk so treffend: Nicht das Werkzeug macht den 
Handwerker aus, sondern ein guter Handwerker erzielt mit jedem Werkzeug
das gewünschte Ergebnis. Wobei selbstverständlich das beste Ergebnis nur
zustande kommt, wenn dem guten Handwerker auch das beste Werkzeug zur 
Verfügung steht.

### Warum ein "neues Home Assistent", wenn das Existierende so gut ist?

Nun, auf den ersten Blick mag es so aussehen, als könnte/müsste man mit Home 
Assistant wunschlos glücklich sein. Tolle Oberfläche, sehr aktive Community, 
sehr umfassende Unterstützung von smarten Geräten, ... Was will man mehr?

Nun, ich persönlich bin der Meinung, das ein Gebäude, das (softwaretechnisch) 
auf wackeligen Beinen steht, nicht besonders stabil und nicht wirklich 
dafür geeignet ist, um sich dort bei einem Erdbeben in Sicherheit zu bringen. 
Ich bin vermutlich zu alt, um die vermehrt aufkommende Grund-Philosophie vieler 
Entwickler, das (vor allem optischer) Schein wichtiger ist, als ein 
durchdachtes Grundgerüst, das auch späteren Anforderungen gerecht wird und 
leicht, ohne das das ganze Gebäude in sich zusammenfällt, erweitert werden kann. 
Wie der Zufall es will, lese ich gerade auch ein Buch ("Hacking - Der umfassende 
Praxis-Guide", von Eric Arnberg und Daniel Schmid, erschienen im mitp-Verlag, 
2. Auflage von 2022), da ich mich schon etwas länger für "Ethisches Hacken", 
also den Test (in diesem Fall) meiner eigenen Schutzmaßnahmen gegen Angriffe 
jeglicher Art von Aussen interessiere. Ich weiß, lesen gehört heutzutage nicht 
mehr zu den Tätigkeiten, die in der Gesellschaft überhaupt und auch 
bei heutigen Entwicklern nicht mehr angesagt sind. Ich bin halt von gestern "und das ist 
gut so", um ein geklautes Zitat zu verwenden. Darin wird ebenfalls auf diese 
um sich greifende Unsitte (meine persönliche Einschätzung) eingegangen, wenn 
auch in einem ganz anderen Zusammenhang. Die Autoren nennen diejenigen, die 
ohne jegliches (oder zumindest mit wenig) Grundwissen, mit wenigen Klicks coole 
Hacks zaubern (oder es zumindest glauben), nicht zu Unrecht "Script-Iddies". 
Wie die Autoren des Buches möchtet ich deshalb alle an der Mitwirkung 
Interessierten, die ohne viel Hintergrundwissen und Engagement "ein paar 
oberflächliche Tricks" lernen oder lehren möchten, darauf aufmerksam machen, 
das sie andere Projekte bestimmt interessanter finden werden (und vielversprechender,
was die Anerkennung der coolen Hacks angeht).

#### Wo bleibt denn der Respekt, vor den Mitgliedern der Community?

Ich möchte hier ganz klar stellen, dass es mir nicht darum geht, jemanden zu 
verunglimpfen oder madig zu machen. Die Home Assistant Community hat trotz 
aller Schwächen am Grundkonzept ein großartiges Werk geschaffen, das aus meiner 
Sicht die beste z.Zt. existierende Umsetzung einer Hausautomation ist, die auf 
Cloud-Services verzichten kann (falls man es wünscht).

Allerdings muss man nur ein wenig an der Oberfläche kratzen (also in den 
Quellcode schauen), damit sich einem die Haare sträuben (zumindest, wenn 
man lange in der Software-Entwicklung tätig war und kaum noch über Haare verfügt, 
die sich noch sträuben können). Natürlich muss man nicht wie 
ich Informatik studiert haben, um an einem Open-Source-Projekt mitzuwirken. 
Genau das macht die Open-Source-Community ja zu einem so großartigem Ort, wo 
genauso viel Platz für "Anfänger" ist, wie für "Fortgeschrittene". Aber wenn 
niemand der "Fortgeschrittenen" die "Anfänger" anleitet und ihnen Tipps gibt, 
wie sie sich weiter entwickeln können und dadurch ihre Ideen besser umsetzen könnten, 
verkümmert aus meiner Sicht ein wichtiger Teil dessen, was diese Community 
leisten kann (und sich selbst offiziell auch auf die Fahnen geschrieben hat):
 **Andere inspirieren**, 
sei es nun die Inspiration bei der gemeinsamen Mitwirkung an einem Projekt oder 
die Inspiration, sich selbst zu verbessern. Nach meiner Erfahrung kann
und sollte man sich immer verbessern, ganz egal, wie viel Erfahrung man
bereits hat. Man kann immer nur einen ganz kleinen Teil der Möglichkeiten 
effizient und vielleicht auch wirklich besser als andere beherrschen. Aber
das ist eben nur ein ganz kleiner Teil der Möglichkeiten, die einem irgendwann
zur Verfügung stehen, wenn man nie glaubt, man wäre der Perfektion so
nahe, das es nichts mehr zu "assimilieren" gibt, um diesem Ziel näher zu
kommenn (Die Borg-Queen lässt schön grüßen.)

#### Hintergrund und meine ganz persönliche Motivation für dieses Projekt

Eigentlich wollte ich "nur" meinen ganz persönlichen "Jarvis" als Integration 
in Home Assistant realisieren, da mir *"die Tante von Google"* etwas zu 
geschwätzig ist (Sorry, Google. Ansonsten bin ich auch mit dem 
Google-Assistenten zufrieden). Da mir ebenfalls die Stimme von *"Tante Google"* 
auf die Dauer "zu nervig" wurde, brauchte ich also als Erstes eine geeignete 
Text-To-Speech Integration. Nichts einfacher als das, dachte ich zumindest. 
Home Assistant hat bereits seit langem eine Integration um Amazon Polly als 
TTS-Service verwenden zu können und bei Polly habe ich auch eine Stimme 
gefunden, die ich als Stimme für "Jarvis" angemessen hielt. Der Service von 
Amazon ist leider nicht kostenlos (von irgendwas muss ja schließlich Jeff Bezos 
seine Weltraumausflüge finanzieren, ohne die die Menschheit als Ganzes und
Jeff Bezos ganz besonders dem Untergang geweiht wären), aber bei der zu 
erwartenden Anzahl von Wörtern, die Amazon pro Monat abrechnen kann, bleiben 
die Kosten in einem vertretbaren Rahmen. 

#### Meine guten Ideen, oder das, was ich dafür hielt

Kaum hatte ich alles am Laufen, wurden die Schwächen des Systems 
offensichtlich. Ich hatte mich bei Polly für zwei unterschiedliche Stimmen 
entschieden. Eine "Neurale" und eine "Standard"-Stimme. Ganz dumme Idee, denn
die Amazon Polly Integration von Home Assistant lässt zwar keine Wünsche bei der 
Grund-Konfiguration von Polly offen, aber wehe, wenn man die blöde Idee hat, 
unterschiedliche Stimmen (kein Problem) mit unterschiedlichen Engines (Autsch, 
wer kann denn an sowas denken, wenn er die Integration schreibt) zu verwenden. 
Also erstmal Polly überarbeiten, macht ja auch Spass etwas zu verbessern.

Als nächste hatte ich die glorreiche Idee, den Ablauf von "Jarvis" Antworten 
und damit die Dialoge zufälliger zu gestalten. Nach langer Suche hatte ich 
eine Lösung gefunden, von der ich mir einiges verspreche. Auch für meine 
"ausgewählte Lösung" existiert bereits lange eine entsprechende Integration. 
Nochmals super, dachte ich zumindest. Wieder auf zwei Integrationen gestossen, 
die nicht vollständig umgesetzt sind. Dumm gelaufen, aber nicht so dramatisch, 
es macht ja Spass ein grossartiges Projekt voran zu bringen.

Und schliesslich hatte ich die beste Idee aller Zeiten (weil ich es nicht 
anders kenne): Zu jeder Zeile Code, die ich für die Entwicklung von "Jarvis" 
schreiben wollte, sollte ein Test existieren, der überprüft, das "Jarvis" so 
funktioniert, wie er angedacht ist. Nun, um ehrlich zu sein, bei meinen 
bisherigen Projekten wurde dieser Aspekt von mir etwas vernachlässigt und es 
existierten häufig nur die unbedingt notwendigen Tests. Aber nachdem ich mich 
lange aus der Software-Entwicklung zurückgezogen hatte, wollte ich es "endlich 
mal" nach allen Regeln der Kunst angehen. Warum auch nicht, es ist nur noch 
Hobby und ich habe keine Deadline, zu der irgendwas fertig sein muss. Nun, du 
vermutest es vermutlich bereits, auch diese Idee war nicht ganz so gut, wie sie 
sich zuerst anhört. Beim ersten Versuch, einen Minimal-Test für meine Version 
der "Amazon Polly" Integration zu schreiben, konnte Home Assistant aufgrund 
zirkulärer Imports nicht importiert werden. Tests waren damit ausgeschlossen.

#### Wie ein Dreizeiler alles zum Rollen brachte

Über die Schwierigkeiten, einen simplen Dreizeiler zu testen, war ich dann 
zugebenerweise "not amused", wie es auf neudeutsch so schön heisst. Aber wer 
lässt sich schon von so ein paar Anfangsschwierigkeiten davon abbringen, sein 
Vorhaben in die Tat umzusetzen? Ich jedenfalls nicht. Also nach allen gängigen 
Regeln in Open-Source-Projekten erstmal den Fehler melden (worauf ich bis heute 
keine Rückmeldung habe). Ich bin ja auch nicht ganz auf den Kopf gefallen (schon wieder meine Selbstwahrnehmung), 
deshalb auch schon mal selbst nach einer Lösung suchen (obwohl ich mich 
garnicht so tief mit den "Verstrickungen" und "Schichten" auseinander setzen 
wollte, es sollte eigentlich doch nur eine bereits existierende Integration 
"aufgepeppt" werden). Um es abzukürzen: **"Schichten"** oder ähnliches gibt es in 
**Home Assistant nicht**. Selbst die (so sollte man annehmen) tiefsten Schichten, 
von den Home Assistant Entwicklern selbst vielversprechend ***core*** genant, 
greifen munter auf "höherliegende Schichten" zu, um gleich selbst irgendwas anzustossen, 
das eindeutig nicht in den Aufgabenbereich des *Kerns** fällt, wie *"Persistant Notifations"*
direkt auszulösen und aufzurufen, und es wundert tatsächlich 
niemanden (so mein Eindruck), das dieser Verstoss gegen das 
**wichtigste Prinzip der Softwareentwicklung** zu Problemen wie zirkulären 
Imports führt. 

#### Leicht gesagt...

Das Prinzip ist leicht ausgesprochen oder aufgeschrieben, 
nämlich **teile und herrsche**, aber es lässt sich häufig nicht so einfach 
umsetzen wie aufschreiben (mal wieder geklaut, aber die Quelle ist 
seit über 2000 Jahren tot und kann sich nicht mehr gegen Copyright-Verstösse 
wehren und überlebende Rechtsnachfolger existieren auch nicht mehr - ein Hoch 
auf Asterix und Obelix, die ihm die Stirn geboten haben). Es erfordert vor 
allem Eines: Die **Disziplin**, sich an die festgelegten Schnittstellen zu halten.
Nun, in der Software-Entwicklung geht es anders als bei Caesar nicht um die Beherrschung 
fremder Völker, sondern um die Beherrschung einer Problemstellung (zumindest 
in den meisten Software-Projekten. Ob Amazon, Microsoft, Google, Facebook, Twitter, ... das auch 
unterschreiben würden????). Wenn man es schafft, eine Problemstellung 
**zu teilen**, möglichst in ein trivales Problem (angestrebte 
Schwierigkeitsstufe: Ist 1 = 1?), und ein immer noch großes, aber eben 
kleineres Problem (am liebsten das gleiche wie vorher, nur kleiner, dann ist 
nämlich die Lösung durch *Rekursion* möglich), dann hat man gewonnen, 
**herrscht** also über das Problem. 

#### DOS oder nicht DOS, das ish hier die Frage

In Zusammenhang mit Home Assistant würde das bedeuten, klar zu definieren, 
welche Aufgaben ***core*** hat (bei Betriebssystemen würde man es *Kern* oder *Kernel* 
nennen und in vieler Hinsicht handelt es sich bei Home Assistant Core um eine Art "Teil-Betriebssystem".
Sorry, ich kann diese Häufung und verwirrende Vielfalt von "cores" nicht vermeiden. Home Assistant
nennt die Art, wie ich Home Assistant installiert habe und betreibe "Home Assistant Core", hat aber
zugleich intern ein Modul "core", das als *Kernel* von Home Assistant angesehen werden kann. 

Ausser also zu definieren, welche Aufgaben der *Kernel* von Home Assistant hat,
würde man natürlich damit auch gleich festlegen, welche Aufgaben er nicht hat 
(eben alles, was nicht ausdrücklich als Aufgabe definiert wurde) und wie bestimmte 
*Ereignisse* an höherliegende Schichten weitergeleitet werden, weil der *Kernel* sozusagen
weiß oder erahnt, das die "höherliegenden Schichten" etwas Einblick in den *Kernel* benötigtigen,
damit sie sinnvoll und reibungslos funktionieren können. Es ist natürlich nicht der Kernel, 
das das "erahnt", sondern es sind die Software-Entwickler (zumindest die, die sich selbst zurecht so nennen),
die wissen, das die "höheren Schichten" Infos vom Kernel benötigen und das das am Besten über das Auslösen
von *Events* funktioniert, weil der *Kernel* hierbei keine Infos über seine Umgebung benötigt, und dadurch
unabhängig vom "Wissen" über das restliche System (also ohne zirkuläre Imports) implementiert werden kann. 
Das suboptimale (schon wieder neudeutsch für "hirnlose") bei der Lösung, 
wie sie in Home Assistant umgesetzt wurde, ist mal wieder, das alle 
Voraussetzungen, um es sauber zu implementieren vorhanden sind. Einige oder viele scheinen aber zu
meinen, das Regeln (wie das vorhandene Event-Benachrichtigungssystem) nur für alte, graue, bald austerbende Entwickler:innen sind. Sie
scheinen sich in ihrer kreativen Freiheit so sehr eingeschränkt zu fühlen, das 
solche wohl definierten, vorhandenen Schnittstellen nur etwas für Nichts-Könner zu sein scheinen.
Und anschließend wundern sie sich über die (nur bei Nicht-Denkenden) nicht zu erwartenden Nebeneffekte. 
Aber vermutlich nicht mal das. Der Effekt stimmt, der Rest interessiert nicht.
Ein Hoch auf die Evolution und kreative Freihet (oder wie heisst das korrekt, wenn sich das Hirn überproportional
zur Größe zur selbst wahrgenommenen Genialität verkleinert?).

Microsoft Windows hatte lange mit den gleichen Schwierigkeiten zu kämpfen, 
und wie ich Microsoft einschätze hat es das noch immer, aber ich arbeite
zum Glück nur noch mit Linux und kann mir über den aktuellen Stand von Windows 
Version HauMichTot kein Urteil mehr erlauben. Als sie mit den merkwürdigen
Erhhöhungen der Versionsnummern begannen (2.0, 3.1, 3.11, 4.0, 95, 98, 2000, 2002, 2003, 7!!!!!, 8, 10!!!!, ...)
hatten sie mich erfolgreich so verwirrt, das ich an den Inhalten meines Studiums
zu zweifeln began (vor allem im Grundstudium bestand ein Informatikstudium mal zu 80 - 90% vor allem aus Mathematik).
Aber zum Glück war ich zu diesem Zeitpunkt bereits nicht mehr darauf angewiesen, beruflich mit Windows zu arbeiten.
Bei diesen früheren Versionen von Windows also,
die selbst, wie bereits PC-DOS und Microsoft-DOS 1.0 bis 6.22, Quick-And-Dirty 
entwickelt wurden (mal wieder mein persönliches Urteil), fingen die Entwickler und vor allem unser geliebter Bill (Gates) 
nach meiner Einschätzung als
Erste damit an, Effekt und Optik wichtiger zu nehmen als die ihnen zugedachte und zugeschriebene
Funktionalität. Das führte zu den von uns so heiss geliebten BSDs (Blue Screens of Death - oder auf deutch: 
Blauen Bildschirmen des Todes). Für nicht so Geschichtskundige - Windows zeigte häufig einen Fehlerbildschirm,
(weiße Schrift auf blauem Grund, deshalb BSD), um danach den Dienst einzustellen (meistens direkt vorm Abspeichern
der Arbeit, die damit nochmal gemacht werden durfte). Dann konnte man erst einmal in Ruhe Kaffee trinken gehen,
und wenn man Glück hatte, lief Windows bereits wieder, nachdem der erforderliche Neustart durchgeführt wurde.
Wer sich zu sehr über die verloren gegangene Arbeit aufregte und beim Neustart nicht so genau hin gesehen hatte, 
wurde prompt mit einer zweiten Tasse Kaffee belohnt, weil er/sie vergessen hatte, den Neustart zu bestätigen und statt
des erwarteten laufenden System, die Frage, ob der Rechner neu gestartet werden soll, präsentiert bekam.
(Ob die von Tschibo oder anderen Kaffee-Röstern damals schon eine Provision bekommen haben? Heute wäre das bestimmt der Fall!) 

So entstand bei uns, den "unter DOS und Windows Leidenden und von Ihnen Gequälten" die gängige Umschreibung für Windows:
*"Sie haben die Position Ihres Mauszeigers verändert. Möchten Sie Windows jetzt neu starten, um die Änderung zu übernehmen?"*,
was natürlich stark übertrieben, aber eben nur übertrieben, war. Es hat scheinbar nicht viel dazu gefehlt, 
damit diese Übertreibung Realität geworden wäre, so oft wie man aufgefordert wurde, den Rechner neu zu starten, weil ...

Dieses Vorgehen wurde von den späteren "Errungenschaften" der Software-Industrie, wie Google (nachdem es die Werbung als
Einnahmequelle für sich entdeckt hatte), Facebook, WhatsApp, Twitter und wie die angeblich unverzichtbaren Tools der heutigen
Gesellschaft sonst so heißen auf die Spitze getrieben, weil jeder massiv mit allen legalen (und manchmal auch mit nicht
ganz so legalen) Tricks versucht, die 5 Sekunden Aufmerksamkeit zu erhaschen, die von heutigen "Usern" dieser Dienste maximal
noch zu erwarten sind. Danach klingelt ja schon der nächste "Dienst an der Menschheit" an und verlangt Aufmerksamkeit
(Quatsch, bietet selbstlos die neuesten Informationen, die für das Überleben der Menschheit als Ganzes und des
Dienstes als *beinaher* **selbstloser, kostenloser Service** - zumindest offiziel - ins Besondere von so entscheidender Bedeutung sind), 
wie z.B. das 100.000.000 (für alle bei denen Mathe schon etwas zurückliegt, das einhundertmillionste) Katzenvideo an,
das nun endlich und endgültig die Menschheit vorm Untergang bewahren wird. GOTT SEI DANK! Sagt den Aposteln von *Nostradamus* 
Bescheid, der erwarte Weltuntergang findet (mal wieder) nicht statt!

Vermutlich regen sich jetzt bei vielen Widerstände. Wie kann der nur... So ein Unverschämheit... Was bildet sich dieser
zurückgebliebene "analoge" Fuzzie ein ... Nun, ich war auch mal jung und habe mit meiner Begeisterung für die sich
bietenden Möglichkeiten der neuen Technik und vollem Einsatz im Rahmen meiner Möglichkeiten dafür gesorgt, das die
Technik sich so entwickelt hat, wie sie es nun einmal getan hat (selbstverständlich war ich dabei nicht massgeblich, 
sondern nur einer von vielen). Rückblickend hätte ich früher auf die Warnungen meiner damaligen Freundin und Mutter
unserer Tochter hören sollen und dem ganzen etwas skeptischer gegenüber stehen. Aber ich war blind vor Begeisterung und
der Aussicht, mein Hobby auch zu meinem Beruf machen zu können. Und da ich durch meine Begeisterung
für diese Technik nicht nur dazu beigetragen habe, das die "Digital Natives", wie sich selbst gerne etwas zu überheblich
nennen, überhaupt etwas haben, von dem sie behaupten können, sie könnten als Einzige wirklich damit umgehen, 
weil sie damit groß geworden sind, sondern dafür auch einen hohen Preis bezahlt habe (aber nicht nur ich, sondern vor allem
unsere Tochter, die viel zu kurz kam, weil ich "ständig die Welt retten" musste oder wollte), nehme ich mir das Recht,
das Ganze auch mal kritisch zu beleuchten, einfach heraus. Wem es nicht passt, der muss es ja nicht
lesen. Telegram verbreitet bestimmt gerade schon die nächste Verschwörungstheorie, die mehr Aufmerksamkeit verdient,
als das Geschwafel eines zurückgebliebenen "analogen" Fuzzies.

Nun, nach diesem nicht vorgesehenem und viel zu langem Ausflug in die Anfänge der Software-Industrie, zurück zum eigentlichen Thema. 
Aber ich musste das einfach mal los werden!

Es geht, oh Wunder, hier um Home Assistant und nicht die Menschheit und deren bevorstehendem Untergang bzw. Rettung vor ihm!
Also, mein Kompliment an die Home Assistant Community. Ich habe noch nichts gesehen, das 
einem BSD ähnelt und bisher hat Home Assistant immer tadellos funktioniert.

#### Endlich die Lösung?

Nun, irgendwann hatte ich eine Lösung für mein Problem gefunden, aber 
der Code wäre in einem "Produktiv-System" nicht mehr zu verwenden gewesen, da 
ich viele Stellen zur Vermeidung der zirkulären Imports nur auskommentieren 
konnte. Schließlich wollte ich nicht das ganze System durchforsten und überarbeiten. Das sollten 
ruhig die machen, die sich damit auskennen und z.T. seit Jahren in der Home 
Assistant Community aktiv sind. Da Home Assistant (zumindest in ihrer eigenen
Dokumentationen für Entwickler, aber wer ausser mir liest so'n Quatsch auch, wenn
er an der Entwicklung des Projekts mitwirken möchte) fordert, das neue Integrationen mit Tests 
(konkret pytest - Tests) auf Herz und Nieren geprüft werden, dachte ich, meine Beiträge, 
wenn auch nicht ausgereift, wären zumindest als Inspiration für die "Wissenden", 
die sich in den Tiefen des System besser auskennen, willkommen. 
So wirklich erfreut, das ihnen jemand ins Handwerk pfuscht (so mein Eindruck), 
war bei Home Assistant aber niemand. Ganz im Gegenteil. Sie vermittelten mir eher 
den Eindruck, dass der Versuch meine Erkenntnisse zu teilen, um damit das Projekt 
voran zu bringen, genauso willkommen sind, wie eine Schmeissfliege auf der 
Frühstücksmarmelade (vielleicht verdient Nabu Casa an der  "Home Assistant Cloud" zu gut, 
um den Open-Source Gedanken noch Ernst zu nehmen).

#### Hurra! Ich habe mein Open-Source-Projekt gefunden

Aber was soll's. So habe ich wenigstens das gefunden, wonach ich so lange 
gesucht habe. Ein Projekt, wo ich mich austoben und meiner Kreativität freien 
Lauf lassen kann. Schöner wäre es natürlich gewesen, Teil einer größeren 
Entwickler-Community zu sein. Aber dieses Projekt muss ja nicht auf Dauer von mir alleine 
gestemmt werden. Vielleicht findet sich der/die Eine oder der/die Andere, die 
ebenfalls Spass an Herausforderungen hat. Und Herausforderungen sind bei diesem 
Mammut-Vorhaben genug zu sehen und noch mehr werden sich im Laufe der Zeit 
ergeben.

### Verbesserungsvorschläge / Fehlerberichte / Serviceanfragen

Wenn du Vorschläge für neue Features hast, einen Fehler melden möchtest oder bei 
einem Problem nicht weiter kommst, schau bitte als Erstes bei 
[Unterstützung und Wartung][support-url] nach. Dort wird ausführlich erläutert, 
wie und wo du dein Anliegen vorbringen kannst.

### Mitwirkung

Mitwirkungen machen die Open-Source-Community zu einem so großartigen Ort zum 
Lernen, Inspirieren und Schaffen. Ich würde mich freuen, wenn du ein neues 
Feature, einen Bugfix oder irgendetwas anderes zu diesem Projekt beitragen 
möchtest. Es ist alles willkommen, daß dieses Projekt voran bringt. Aber bitte 
lies zuerst [Mitwirkung][contribute-url] an diesem Projekt und den 
[Verhaltenskodex][coc-url] für Mitwirkende, **bevor** du mit dem Programmieren 
beginnst.

### Danksagungen

Mein Dank gilt allen, die mein Vorhaben unterstützt haben oder noch unterstützen 
werden und die aktiv an der Realisierung mitwirken oder durch neue Sichtweisen 
und Vorschläge für Verbesserungen dazu beitragen oder bereits beigetragen haben, 
meine anfängliche Idee weiter zu verfeinern und abzurunden. Ebenfalls bedanken 
möchte ich mich bei allen, deren Vorarbeit ich für die Realisierung dieses 
Vorhabens verwenden darf. 

Besonders und ausdrücklich möchte ich allerdings meiner Freundin für Ihr 
Verständnis und Ihre Unterstützung danken, ohne die meine Vision nie 
Wirklichkeit wird (weil es oft darauf hinaus läuft, das ich bis spät in der 
Nacht und am Wochenende an der Umsetzung und Verfeinerung meiner Idee sitze 
und deshalb für gemeinsame Aktivitäten weniger Zeit übrig bleibt, als sie 
verdient hätte).

### Lizenz

Veröffentlicht zur freien Verwendung/Modifizierung gemäß den Bedingungen der 
[Allgemeinen Öffentlichen GNU-Lizenz v3][license-url].

Aber "Liebe Liebenden" (wie es Brisko Schneider gesagt hätte), immer daran denken:

**Dies ist freie Software, ohne irgendeine Garantie auf Funktionalität oder 
Verwendbarkeit für einen bestimmten Zweck.**

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[logo]: images/logo.svg
[project-url]: https://homeassistant.io

[license-badge]: images/license.de.svg
[license-url]: ../COPYRIGHT.de.md

[version-badge]: images/version.svg
[version-url]: https://github.com/nixe64/Home-Assistant-Blueprint/releases

[issues-url]: https://github.com/nixe64/Home-Assistant-Blueprint/issues
[bugs-badge]: https://img.shields.io/github/issues/nixe64/Home-Assistant-Blueprint/bug.svg?label=Fehlerberichte&color=informational
[bugs-url]: https://github.com/nixe64/Home-Assistant-Blueprint/issues?utf8=✓&q=is%3Aissue+is%3Aopen+label%3Abug

[contribute-url]: contributing/Contribute.de.md
[coc-url]: contributing/CodeOfConduct.de.md

[template-btn]: images/template-btn.svg

[support-url]: Support.de.md
[development-url]: Development.de.md
