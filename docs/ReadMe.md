<a href="ReadMe.en.md"><img src="images/en.svg" valign="top" align="right"/></a>
<a href="ReadMe.md"><img src="images/de.svg" valign="top" align="right"/></a>
[![Version][version-badge]][version-url]
[![License][license-badge]][license-url]
<!--
[![Bugs][bugs-badge]][bugs-url]
-->

[![Logo][logo]][project-url]

"Live Long And Prosper"! Hier kommst sie - die nächste Entwicklungstufe der 
Hausautomation. Sie basiert auf Home Assistent, dem zurecht beliebten zentralen
Steuerungssystems in einem Smart Home oder Smart House. Wie Home Assistent ist 
es ebenfalls als kostenlose und quelloffene Software konzipiert, die in den 
wesentlichen Teilen in Python entwickelt wird und deren Hauptaugenmerk auf 
lokaler Steuerung und Privatspäre liegt. Da ich mich allerdings in der C / 
C++ / C# - Entwicklung mehr zuhause fühle, werden viele unterstützende 
Bibliotheken eher in C++ entwickelt werden. Aus dem gleichen Grund werde ich 
das eher auf einer "Modulhierarchie" bestehende Grundgerüst (so gut es Python 
eben zulässt) auf eine Klassenhierarchie umstellen, wo jedem, der sich mit 
Klassenhierarchien etwas auskennt aber auch "Einsteigern", relativ schnell klar
wird, welche Klasse welche Aufgaben übernimmt, welche Teile der "Schnittstelle" 
von allen benutzt werden dürfen und welche Teile nur innerhab der Klasse für die 
Implementierung der Funktionalität vorhanden sind und eben **NICHT** von allen 
aufgerufen werden dürfen. Leider unterstützt Python die Verwendung von 
(Achtung, C++ - Code) ```private``` oder ```protected``` in Klassen nicht,
so das ich "nur" darauf vertrauen kann, das die nicht öffentlichen Teile der 
Implementierung, von denen, die dieses Projekt für sinnvoll und interessant
halten, als nicht öffentliche Teile der Implementierung respektiert werden.

### Warum ein "neues Home Assistent", wenn das existierende kaum Wünsche offen lässt?

Nun, auf den ersten Blick mag es so aussehen, als könnte/müsste man mit Home 
Assistant wunschlos glücklich sein. Tolle Oberflöche, sehr aktive Community, 
sehr umfassende Unterstützung von smarten Geräten, ... Was will man mehr?

Nun, ich persönlich bin der Meinung, das ein Gebäude, das (softwaretechnisch) 
auf wackeligen Beinen steht, nicht besonders stabil ist und nicht wirklich 
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
mehr zu den Tätigkeiten, die in der Gesellschaft überhaupt und scheinbar auch 
bei heutigen Entwicklern angesagt sind, ich bin halt von gestern "und das ist 
gut so", um ein geklautes Zitat zu verwenden. Darin wird ebenfalls auf diese 
um sich greifende Unsitte (meine persönliche Einschätzung) eingegangen (wenn 
auch in einem ganz anderen Zusammenhang). Die Autoren nennen diejenigen, die 
ohne jegliches (oder zumindest mit wenig) Grundwissen, mit wenigen Klicks coole 
Hacks zaubern (oder es zumindest glauben), nicht zu Unrecht "Script-Iddies". 
Wie die Autoren des Buches möchtet ich deshalb alle an der Mitwirkung 
Interessierten, die ohne viel Hintergrundwissen und Engagement "ein paar 
oberflächliche Tricks" lernen oder lehren wollen, darauf aufmerksam machen, 
das sie andere Projekte bestimmt interessanter finden.

### Wo bleibt denn der (auf von mir geforderte) Respekt, vor den Mitgliedern der Open-Source-Community?

Ich möchte hier ganz klar stellen, dass es mir nicht darum geht, jemanden zu 
verunglimpfen oder madig zu machen. Die Home Assistant Community hat trotz 
aller Schwächen am Grundkonzept ein großartiges Werk geschaffen, das aus meiner 
Sicht die beste z.Zt. existierende Umsetzung einer Hausautomation ist, die auf 
Cloud-Services verzichten kann (falls man es wünscht).

Allerdings muss man nur ein wenig an der Oberfläche kratzen (also in den 
Quellcode schauen), damit sich einem die Haare sträuben (zumindest, wenn 
man lange in der Software-Entwicklung tätig war). Natürlich muss man nicht wie 
ich Informatik studiert haben, um an einem Open-Source-Projekt mitzuwirken. 
Genau das macht die Open-Source-Community ja zu einem so großartigem Ort, wo 
genauso viel Platz für "Anfänger" ist, wie für "Fortgeschrittene". Aber wenn 
niemand der "Fortgeschrittenen" die "Anfänger" anleitet und ihnen Tipps gibt, 
wie sie sich weiter entwickeln und dadurch ihre Ideen besser umsetzen können, 
verkümmert aus meiner Sicht ein wichtiger Teil dessen, was diese Community 
leisten kann (und sich selbst offiziell auch auf die Fahnen geschrieben hat):
 **Andere inspirieren**, 
sei es nun die Inspiration für das gemeinsame Projekt oder die Inspiration, 
sich selbst zu verbessern. 

### Hintergrund und meine ganz persönliche Motivation für dieses Projekt

Eigentlich wollte ich "nur" meinen ganz persönlichen "Jarvis" als Integration 
in Home Assistant realisieren, da mir "die Tante von Google" etwas zu 
geschwätzig ist (Sorry, Google. Ansonsten bin ich auch mit dem 
Google-Assistenten zufrieden). Da mir ebenfalls die Stimme von *"Tante Google"* 
auf die Dauer "zu nervig" wurde, brauchte ich also als Erstes eine geeignete 
Text-To-Speech Integration. Nichts einfacher als das (dachte ich zumindest). 
Home Assistant hat bereits seit langem eine Integration um Amazon Polly als 
TTS-Service verwenden zu können und bei Polly habe ich auch eine Stimme 
gefunden, die ich als Stimme für "Jarvis" angemessen hielt. Der Service von 
Amazon ist leider nicht kostenlos (von irgendwas muss ja auch Jeff Bezos seine 
Weltraumausflüge bezahlen), aber bei der zu erwartenden Anzahl von Wörtern, 
die Amazon pro Monat abrechnen kann, bleiben die Kosten in einem vertretbaren 
Rahmen. Kaum hatte ich alles am Laufen, wurden die Schwächen des Systems 
offensichtlich. Ich hatte mich bei Polly für zwei unterschiedliche Stimmen 
entschieden. Eine "Neurale" und eine "Standard"-Stimme. Ganz dumme Idee, denn
die Amazon Polly Integration lässt zwar keine Wünsche bei der 
Grund-Konfiguration von Polly offen, aber wehe, wenn man die blöde Idee hat, 
unterschiedliche Stimmen (kein Problem) mit unterschiedlichen Engines (Autsch, 
wer kann denn an sowas denken, wenn er die Integration schreibt) zu verwenden. 
Also erstmal Polly überarbeiten, macht ja auch Spass etwas zu verbessern.

Als nächste hatte ich die glorreiche Idee, den Ablauf von "Jarvis" Antworten 
und damit die Dialoge zufälliger zu gestalten. Nach langer Suche hatte ich 
eine Lösung gefunden, von der ich mir einiges verspreche. Auch für meine 
"ausgewählte Lösung" existiert bereits lange eine entsprechende Integration. 
Nochmals super, dachte ich zumindest. Wieder auf zwei Integrationen gestossen, 
die nicht vollständig umgesetzt sind. Dumm gelaufen, aber nicht schlimm, 
es macht ja Spass ein grossartiges System voran zu bringen.

Und schliesslich hatte ich die beste Idee aller Zeiten (weil ich es nicht 
anders kenne): Zu jeder Zeile Code, die ich für die Entwicklung von "Jarvis" 
schreiben wollte, sollte ein Test existieren, der überprüft, das "Jarvis" so 
funktioniert, wie es angedacht ist. Nun, um ehrlich zu sein, bei meinen 
bisherigen Projekten wurde dieser Aspekt von mir etwas vernachlässigt und es 
existierten häufig nur die unbedingt notwendigen Tests. Aber nachdem ich mich 
lange aus der Software-Entwicklung zurückgezogen hatte, wollte ich es "endlich 
mal" nach allen Regeln der Kunst angehen. Warum auch nicht, es ist nur noch 
Hobby und ich habe keine Deadline, zu der irgendwas fertig sein muss. Nun, du 
vermutest es vermutlich bereits, auch diese Idee war nicht ganz so gut, wie es 
sich zuerst anhört. Beim ersten Versuch, einen Minimal-Test für meine Version 
der "Amazon Polly" Integration zu schreiben, konnte Home Assistant aufgrund 
zirkulärer Imports nicht importiert werden. Tests waren damit ausgeschlossen.

Über die Schwierigkeiten, einen simplen Dreizeiler zu testen, war ich dann 
zugebenerweise "not amused", wie es auf neudeutsch so schön heisst. Aber wer 
lässt sich schon von so ein paar Anfangsschwierigkeiten davon abbringen, sein 
Vorhaben in die Tat umzusetzen? Ich jedenfalls nicht. Also nach allen gängigen 
Regeln in Open-Source-Projekten erstmal den Fehler melden (worauf ich bis heute 
keine Rückmeldung habe). Ich bin ja auch nicht ganz auf den Kopf gefallen, 
deshalb auch schon mal selbst nach einer Lösung suchen (obwohl ich mich 
garnicht so tief mit den "Verstrickungen" und "Schichten" auseinander setzen 
wollte, es sollte eigentlich doch nur eine bereits existierende Integration 
"aufgepeppt" werden). Um es abzukürzen "Schichten" oder ähnliches gibt es in 
Home Assistant nicht. Selbst die (so sollte man annehmen) tiefsten Schichten, 
von Home Assistant selbst ```core``` genant, greifen munter auf "höherliegende 
Schichten", wie "Persistant Notifations" zu, und es wundert tatsächlich 
niemanden (so mein Eindruck), das dieser Verstoss gegen das 
**wichtigste Prinzip der Softwareentwicklung** zu Problemen wie zirkulären 
Imports führt. Das Prinzip ist leicht ausgesprochen oder aufgeschrieben, 
nämlich **teile und herrsche**, aber es lässt sich häufig nicht so einfach 
umsetzen wie aufschreiben. Es erfordert vor allem Eines: Die Disziplin, sich an 
die festgelegten Schnittstellen zu halten (mal wieder geklaut, aber die Quelle ist 
seit über 2000 Jahren tot und kann sich nicht mehr gegen Copyright-Verstösse 
wehren und überlebende Rechtsnachfolger existieren auch nicht mehr - ein Hoch 
auf Asterix und Obelix, die ihm die Stirn geboten haben). Nun, in der 
Software-Entwicklung geht es anders als bei Caesar nicht um die Beherrschung 
fremder Völker, sondern um die Beherrschung einer Problemstellung (zumindest 
in den meisten Software-Projekten. Ob Amazon und Microsoft das auch 
unterschreiben würden????). Wenn man es schafft, eine Problemstellung 
**zu teilen**, möglichst in ein trivales Problem (angestrebte 
Schwierigkeitsstufe: Ist 1 = 1?), und ein immer noch großes, aber eben 
kleineres Problem (am liebsten das gleiche wie vorher, nur kleiner, dann ist 
nämlich die Lösung durch *Rekursion* möglich), dann hat man gewonnen, 
**herrscht** also über das Problem. 

In Zusammenhang mit Home Assistant würde das bedeuten, klar zu definieren, 
welche Aufgaben ```core``` hat (bei Betriebssystemen würde man es wohl Kern 
nennen) und welche Aufgaben nicht und dabei ebenfalls festzulegen, wie besimmte 
*Ereignisse* an höherliegende Schichten weitergeleitet werden (von denen der 
Kern aber nicht mehr weiß, als **"es gibt höherliegende Schichten, die in geeigneter Weise über bestimmte Ereignisse informiert werden wollen"**). Microsoft Windows hatte lange mit den gleichen Schwierigkeiten zu kämpfen, 
selbst, wie bereits PC-DOS und Microsoft-DOS 1.0 bis 6.22, Quick-And-Dirty 
(mal wieder meine persönliche Einschätzung) entwickelt, führte das zu den 
von uns so heiss geliebten BSDs (Blue Screens of Death - oder auf deutch: 
Blauen Bildschirmen des Todes). Wer nicht weiß, worauf ich anspiele möge Wiki 
oder eine andere Geschichtssammlung oder Dokumentation über die Anfänge der
Computer-Industrie befragen, wenn er/sie es verstehen möchte. So gesehen mein 
Kompliment an die Home Assistant Community. Ich habe noch nichts gesehen, das 
einem BSD ähnelt und bisher hat Home Assistant immer funktioniert.

Nun, irgendwann hatte ich eine Lösung für mein aktuelles Problem gefunden, aber 
der Code wäre in einem "Produktiv-System" nicht mehr zu verwenden gewesen, da 
ich viele Stellen zur Vermeidung der zirkulären Imports nur auskommentieren 
konnte. Schließlich wollte ich nicht das ganze System durchforsten. Das sollten 
ruhig die machen, die sich damit auskennen und z.T. seit Jahren in der Home 
Assistant Community aktiv sind. Da Home Assistant (zumindest in ihrer eigenen
Dokumentation für Entwickler) fordert, das neue Integrationen mit Tests 
(konkret pytest) auf Herz und Nieren geprüft werden (sehr vernünftig und 
lobenswert), dachte ich, meine Beiträge, wenn auch nicht ausgereift, wären
zumindest als Inspiration für die "Wissenden", die sich in den Tiefen des 
System besser auskennen, willkommen. So wirklich erfreut, das ihnen jemand ins 
Handwerk pfuscht (so mein Eindruck), war bei Home Assistant aber niemand. Ganz 
im Gegenteil. Sie vermittelten mir eher den Eindruck, dass der Versuch meine 
Erkenntnisse zu teilen, um damit das Projekt voran zu bringen, genauso 
willkommen sind, wie eine Schmeissfliege auf der Frühstücksmarmelade 
(vielleicht verdient Nabu Casa aber auch einfach nur zu gut an der 
"Home Assistant Cloud", um den Open-Source Gedanken noch Ernst zu nehmen).

Aber was soll's. So habe ich wenigstens das gefunden, wonach ich so lange 
gesucht habe. Ein Projekt, wo ich mich austoben und meiner Kreativität freien 
Lauf lassen kann. Schöner wäre es natürlich gewesen, Teil einer größeren 
Entwickler-Community zu sein. Aber dieses Projekt muss ja nicht von mir alleine 
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
