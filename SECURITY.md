# Security

Security fixes are applied to the latest `main` branch. The static GitHub Pages app stores resume/card information in the user's browser; it does not provide server-side account authentication. The optional `webcontrol` backend is separate and must be deployed with HTTPS, private environment secrets, and persistent database storage.

Do not put admin passwords, password hashes intended for another service, token secrets, or private API keys in website JavaScript or GitHub. Keep backend secrets in the hosting provider's private environment settings. The public `webcontrol-config.js` is only for the API's public URL.

To report a vulnerability, use GitHub's private vulnerability reporting for this repository if it is enabled. Otherwise contact the repository owner privately before publishing details. Please include the affected page or endpoint and steps to reproduce; do not include real user data or active credentials.
