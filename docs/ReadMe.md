<a href="ReadMe.en.md"><img src="images/en.svg" valign="top" align="right"/></a>
<a href="ReadMe.md"><img src="images/de.svg" valign="top" align="right"/></a>
[![Version][version-badge]][version-url]
[![License][license-badge]][license-url]
<!--
[![Bugs][bugs-badge]][bugs-url]
-->

### Home Assistant Blueprint
<br/>

[![Logo][logo]][project-url]

<br/>

Weiterentwicklung eines Home Assistant Blueprints, um ein neues Repositorie mit der erforderlichen Verzeichnisstruktur und den wichtigsten Tools
für Entwicklung einer neuen Home Assistant Integration (Custom Component) anzulegen.

### Verwendung

Um diese Vorlage für dein eigenes Projekt zu verwenden, nutze einfach diesen Button ![btn][template-btn] in der Repository-Ansicht auf GitHub oder klone dieses Repository. Dann lösche die Datei ```custom_components/DELETE-ME```. Ich habe sie in dieses Blueprint aufgenommen, damit git das für die Entwicklung einer eigenen Home Assistant Integration benötigte Verzeichnis automatisch anlegt. In custom_components musst du dann einen neuen Ordner für deine Integration anlegen, in den dann der Quelltext kommt. Der Name des Ordners sollte in etwa so heißen wie deine neue Integration,
damit sie als **neue** Integration in Home Assistant erkannt und zugelassen werden kann. (Siehe auch die Entwicklerdokumentationen auf <https://developers.home-assistant.io/> und <https://hacs.xyz/docs/developer/start>).

Ich verwende in allen Repositories den GitGuardian Shield, um zu verhindern, dass ich versehentlich sensible Daten wie Zugangsdaten zu bezahlten Diensten im Quellcode auf GitHub öffentlich zugänglich mache (vor allem in den Tests der Implementierung). Ich rate dir dringend, dies für deine Projekte ebenfalls zu erwägen, weil es teuer für dich werden kann, wenn diese Daten in die falschen Hände geraten. Falls du diese Überprüfung nicht wünscht, lösche die Datei ```.github/workflows/gitguardian.yml``` und passe die pre-commit Überprüfungen an, indem du in der Datei ```.pre-commit-config.yaml``` den "Hook" mit der id ```ggshield``` entfernst. Falls du mit der Überprüfung einverstanden bist, lies bitte als nächstes [Einrichtung der Entwicklungsumbebung][development-url]. Dort werden die Konfiguration des GitGuardian Shields und die notwendigen Vorbereitungen der Repositories ausführlich behandelt. Es würde den Rahmen dieser ReadMe sprengen, hier auf die Details einzugehen.

Alle, die sie gegen die Überprüfung durch den GitGuardian Shield entschieden haben, sollten allerdings auch als nächstes [Einrichtung der Entwicklungsumgebung][development-url] lesen und den ersten Punkt dann überspringen.

### Verbesserungsvorschläge / Fehlerberichte / Serviceanfragen

Wenn du Vorschläge für neue Features hast, einen Fehler melden möchtest oder bei einem Problem nicht weiter kommst, schau bitte als Erstes bei [Unterstützung und Wartung][support-url] nach. Dort wird ausführlich erläutert, wie und wo du dein Anliegen vorbringen kannst.

### Mitwirkung

Mitwirkungen machen die Open-Source-Community zu einem so großartigen Ort zum Lernen, Inspirieren und Schaffen. Ich würde mich freuen, wenn du ein neues Feature, einen Bugfix oder irgendetwas anderes zu diesem Projekt beitragen möchtest. Es ist alles willkommen, daß dieses Projekt voran bringt. Aber bitte lies zuerst [Mitwirkung][contribute-url] an diesem Projekt und den [Verhaltenskodex][coc-url] für Mitwirkende, **bevor** du mit dem Programmieren beginnst.

### Danksagungen

Mein Dank gilt allen, die mein Vorhaben unterstützt haben oder noch unterstützen werden und die aktiv an der Realisierung mitwirken oder durch neue Sichtweisen und Vorschläge für Verbesserungen dazu beitragen oder bereits beigetragen haben, meine anfängliche Idee weiter zu verfeinern und abzurunden. Ebenfalls bedanken möchte ich mich bei allen, deren Vorarbeit ich für die Realisierung dieses Vorhabens verwenden darf. 

Besonders und ausdrücklich möchte ich allerdings meiner Freundin für Ihr Verständnis und Ihre Unterstützung danken, ohne die meine Vision nie Wirklichkeit wird (weil es oft darauf hinaus läuft, das ich bis spät in der Nacht und am Wochenende an der Umsetzung und Verfeinerung meiner Idee sitze und deshalb für gemeinsame Aktivitäten weniger Zeit übrig bleibt, als sie verdient hätte).

### Lizenz

Lizensiert gemäß der [Allgemeinen Öffentlichen GNU-Lizenz v3.0][license-url].

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[logo]: images/hassio-icon.png
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
