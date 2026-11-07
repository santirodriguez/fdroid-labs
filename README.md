# Android source-build lab

This repository contains disposable, manually triggered build experiments for published open-source Android projects.

The workflows run on **standard GitHub-hosted Linux runners**. They do not publish apps, sign production packages, or submit anything to a third-party app store. Source inputs are pinned and checked; local build tests must operate without network access or authentication credentials.

There are no scheduled, push, or pull-request workflow triggers. A successful local test is not proof of acceptance by any app store.

## Sudokura

The Sudokura experiment uses the publicly released source at a fixed Git commit and produces only diagnostic records. It must not change the application repository or its published releases. Do not add credentials, tokens, signing keys, or user data to this repository.

See the manual workflow in `.github/workflows/` after it has been reviewed and enabled.
