# Release automation

[`release.yml`](../.github/workflows/release.yml) runs
[release-please](https://github.com/googleapis/release-please) on every push to `master`.
It keeps a release pull request open that bumps `pyproject.toml`,
`custom_components/facilioo/manifest.json` and `uv.lock` and updates `CHANGELOG.md` from the
Conventional Commit titles of squash-merged pull requests. Merging that pull request creates
the `vX.Y.Z` tag and the GitHub release that HACS installs. Nothing is built or uploaded.

## Why a GitHub App token

Pull requests, tags and releases created with the workflow's `GITHUB_TOKEN` do not trigger
other workflows. With it, CI, Hassfest, HACS validation and the PR title check would not run on
the release pull request, and none of them could be a required check. The
[release-please-action documentation](https://github.com/googleapis/release-please-action#other-actions-on-release-please-prs)
recommends a separate token for this case. release-please therefore authenticates as a GitHub
App, using [`actions/create-github-app-token`](https://github.com/actions/create-github-app-token).

The documentation's example is a personal access token; an App token is used instead because
it is created per run, expires
after one hour, is limited to the repositories the App is installed on and to the permissions
the workflow requests, and is not tied to a maintainer's personal account.

## One-time setup

One App can serve several of the maintainer's repositories. If it already exists, skip to
step 3.

1. Under **Settings → Developer settings → GitHub Apps → New GitHub App**, create an App:
   - **GitHub App name**: any unique name; release commits are authored as `<name>[bot]`.
   - **Homepage URL**: the repository URL.
   - **Webhook**: clear **Active**; the App receives no events.
   - **Repository permissions**: **Contents** read and write, **Pull requests** read and
     write. **Metadata** read-only is added automatically. Grant nothing else.
   - **Where can this GitHub App be installed?**: **Only on this account**.
2. On the App's page, note the **Client ID** and use **Generate a private key**; the browser
   downloads a `.pem` file.
3. Under **Install App**, install the App on **Only select repositories** and include this
   repository (for an existing installation: **Configure → Repository access**).
4. Store the credentials in the repository, then delete the local `.pem` file:

   ```bash
   gh variable set APP_CLIENT_ID --repo dirrgang/home-assistant-facilioo --body "<client ID>"
   ```

   ```bash
   gh secret set APP_PRIVATE_KEY --repo dirrgang/home-assistant-facilioo < path/to/private-key.pem
   ```

5. After the first release pull request has been opened by the App, clear **Allow GitHub
   Actions to create and approve pull requests** under **Settings → Actions → General**;
   no workflow needs it any more.

The token requests only `contents: write` (release branch, tag, GitHub release) and
`pull-requests: write` (open, update and label the release pull request). release-please's
documentation also lists `issues: write`, but labelling the release pull request works with
`pull-requests: write`, as the releases up to 0.3.1 showed with `GITHUB_TOKEN`.

## Key rotation and failures

To rotate the key, generate a new private key on the App's page, replace the
`APP_PRIVATE_KEY` secret in every repository that uses the App, and delete the old key there.

If the client ID or key is missing or invalid, the token step fails and the run stops before
release-please starts: no release pull request, tag or release is created, and nothing else is
affected. Fix the credentials and re-run the failed workflow run.
