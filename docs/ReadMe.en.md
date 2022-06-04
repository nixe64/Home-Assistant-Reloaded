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

Derivative of a Home Assistant Blueprint to set up a new repository with the required directory structure and the most important tools
to develop a new Home Assistant Integration (Custom Component).

### Usage

To use this template for your own project, just use this button ![btn][template-btn] in the repository view on GitHub or clone this repository. Then delete the ``custom_components/DELETE-ME`` file. I included it in this blueprint so that git will automatically create the directory needed to develop a custom Home Assistant integration. In custom_components you then need to create a new folder for your integration, where the source code will go. The name of the folder should be something like your new integration,
so that it can be recognized and approved as a **new** integration in Home Assistant. (See also the developer documentation at <https://developers.home-assistant.io/> and <https://hacs.xyz/docs/developer/start>).

I use GitGuardian Shield in all repositories to prevent accidentally making sensitive data like credentials for paid services publicly available in the source code on GitHub (especially in implementation tests). I urge you to consider this for your projects as well, because it can be expensive for you if this data falls into the wrong hands. If you don't want this check, delete the file ``.github/workflows/gitguardian.yml`` and adjust the pre-commit checks by removing the "hook" with id ``ggshield`` in the file ``.pre-commit-config.yaml``. If you agree with the check, please read [Setting up the development environment][development-url] next. There, the configuration of the GitGuardian shield and the necessary preparations of the repositories are covered in detail. It is beyond the scope of this ReadMe to go into the details here.

However, all those who have decided against checking through the GitGuardian Shield should also read [Setting up the development environment][development-url] next and then skip the first point.

### Feature Requests / Bug Reports / Service Requests

If you have suggestions for new features, want to report a bug, or get stuck on a problem, please first check [Support and Servicing][support-url]. It explains in detail how and where you can make your case.

### Contributing

Contributions are what make the open source community such a great place to learn, inspire, and create. I would be happy if you would like to contribute a new feature, bugfix or anything else to this project. Anything that makes this project better is welcome. But please read [Contributions][contribute-url] to this project and the [Code of Conduct][coc-url] for contributors first **before** you start coding.

### Acknowledgements

My thanks go to all those who have supported or will continue to support my project and who are actively involved in its realization or who have contributed or already contributed to the refinement and completion of my initial idea with a new point of view and suggestions for improvements. I would also like to thank everyone whose preparatory work I have been able to use for the realization of this project. 

However, I would like to express my gratitude to my friend for her understanding and support, without which my vision will never become a reality (because it often amounts to me sitting late at night and at weekends on the implementation and refinement of my idea, leaving less time for joint activities than she should have deserved).

### License

Licensed under the [GNU General Public License v3.0][license-url].

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[logo]: images/hassio-icon.png
[project-url]: https://homeassistant.io

[license-badge]: images/license.en.svg
[license-url]: ../COPYRIGHT.en.md

[version-badge]: images/version.svg
[version-url]: https://github.com/nixe64/Home-Assistant-Blueprint/releases

[issues-url]: https://github.com/nixe64/Home-Assistant-Blueprint/issues
[bugs-badge]: https://img.shields.io/github/issues/nixe64/Home-Assistant-Blueprint/bug.svg?label=Fehlerberichte&color=informational
[bugs-url]: https://github.com/nixe64/Home-Assistant-Blueprint/issues?utf8=✓&q=is%3Aissue+is%3Aopen+label%3Abug

[contribute-url]: contributing/Contribute.en.md
[coc-url]: contributing/CodeOfConduct.en.md

[template-btn]: images/template-btn.svg

[support-url]: Support.en.md
[development-url]: Development.en.md
