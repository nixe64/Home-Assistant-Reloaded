<a href="INFO.en.md"><img src="docs/images/en.svg" valign="top" align="right"/></a>
<a href="INFO.md"><img src="docs/images/de.svg" valign="top" align="right"/></a>
[![Version][version-badge]][version-url]
[![License][license-badge]][license-url]

### Amazon Polly for Home Assistant
<br/>

[![Logo][logo]][polly-url]

<br/>

Custom Home Assistant integration for [Amazon Polly][polly-url].

This integration extents the [Amazon Polly Integration][hass-polly] of [Home Assistant][hass-url].

It allows the use of all configuration variables of the original Amazon Polly Integration in the Options field of the service call (e.g. amazon_polly_say). For security reasons the **aws_access_key_id** and **aws_secret_access_key** are excluded.

### License

Licensed under the [GNU General Public License v3.0][license-url]. The [Source Code][github] can be found in my GitHub Repository.


[license-badge]: docs/images/license.en.svg
[license-url]:LICENSE.en.md

[version-badge]: docs/images/version.svg
[version-url]: https://github.com/nixe64/Home-Assistant-Blueprint/releases

[logo]: docs/images/polly.png
[polly-url]: https://aws.amazon.com/polly/
[hass-url]: https://www.home-assistant.io/
[hass-polly]: https://www.home-assistant.io/integrations/amazon_polly/
[github]: https://github.com/nixe64/Home-Assistant-Blueprint