# Wot UI development tools

Open Wot provides component knowledge, MCP tools and AI development skills.
This setup does not migrate native mini-program pages or deploy the app.

## Setup

Use Node.js 20 or newer. Run `npm ci` in the repository root. Commit the
package-lock.json file for reproducible installs. CLI 1.1.0 is pinned in both
package.json and .codex/config.toml.

Open E:\playnow as a trusted Codex project, then restart Codex to load the
project MCP configuration. Do not edit trust settings automatically.

The project includes these official skills under .agents/skills:

- wot-ui-v2: component selection and Vue 3 page development.
- wot-ui-cli: CLI queries and MCP troubleshooting.
- create-wot-ui-theme: reusable SCSS theme creation.

## Commands

```sh
npm run wot -- info Button
npm run wot -- demo Button
npm run wot -- token Button
npm run wot:agent:doctor
npm run wot:lint -- <frontend-directory>
```

The doctor checks configuration, skills, instructions and a real MCP
handshake. It may exit nonzero with action-required until Codex loads the
trusted project, even when the handshake passes.

The UI runtime is not installed yet. During the uni-app migration, install
an exact @wot-ui/ui version. Before then, knowledge queries use the bundled
fallback dataset unless --version is specified. Do not confuse the dataset
version with an installed application dependency.

Wot lint checks component usage; it does not replace TypeScript, uni-app
builds, business tests, or release validation. Run it against the new Vue
frontend once those pages exist. Do not interpret a clean scan of the legacy
WXML frontend as validation of the migration.

The miniprogram-ci dependency belongs to the existing upload setup. Installing
Open Wot does not verify that upload tool or configure production publishing.

## Sources

- https://github.com/wot-ui/open-wot
- https://wot-ui.cn/guide/skills.html
- https://cli.wot-ui.cn
