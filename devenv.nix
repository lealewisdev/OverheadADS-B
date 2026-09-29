{ pkgs, ... }:

{
  languages.python = {
    enable = true;
    venv.enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  packages = [
    pkgs.prek
    pkgs.hadolint
    pkgs.docker
    pkgs.docker-buildx
    pkgs.trivy
    pkgs.updatecli
    pkgs.sops
    pkgs.age
    pkgs.secretspec
    pkgs.typos
    pkgs.ansible-lint
    pkgs.trufflehog
    pkgs.yamllint
    pkgs.commitizen
    pkgs.markdownlint-cli
    pkgs.ruff
    pkgs.renovate
  ];

  git-hooks.package = pkgs.prek;

  git-hooks.hooks = {
    shellcheck.enable = true;
    shellcheck.stages = [ "pre-commit" ];

    hadolint.enable = true;
    hadolint.stages = [ "pre-commit" ];

    trufflehog.enable = true;
    trufflehog.stages = [ "pre-commit" ];

    commitizen.enable = true;
    commitizen.stages = [ "commit-msg" ];

    # Isn't respecting config path an i dont have time to fix it
    # ansible-lint.enable = true;
    # ansible-lint.settings.configPath = ".config/.ansible-lint.yml";
    # ansible-lint.settings.subdir = "ansible";
    # ansible-lint.stages = [ "pre-commit" ];

    typos.enable = true;
    typos.settings.configPath = ".config/_typos.toml";
    typos.settings.diff = true;
    typos.files = "(^|/)README\\.md$";
    typos.stages = [ "pre-commit" ];

    # Isn't respecting config path an i dont have time to fix it
    # yamllint.enable = true;
    # yamllint.files = "^(\\.forgejo/workflows)/";
    # yamllint.stages = [ "pre-commit" ];
    # yamllint.settings.configPath = ".config/.yamllint.yml";

    ruff.enable = true;
    ruff-format.enable = true;
    ruff.stages = [ "pre-commit" ];
    ruff.excludes = [ "typings" ".ansible" ];
    ruff-format.excludes = [ "typings" ".ansible" ];

    uv-lock.enable = true;
    uv-lock.stages = [ "pre-commit" ];

    markdownlint.enable = true;
    markdownlint.settings.configuration = builtins.fromJSON (builtins.readFile .config/.markdownlint.jsonc);
    markdownlint.stages = [ "pre-commit" ];

    uv-audit = {
      enable = true;
      entry = "uv audit --frozen";
      files = "^(uv\\.lock|pyproject\\.toml)$";
      pass_filenames = false;
    };

    renovate-config-validator = {
      enable = true;
      entry = "renovate-config-validator";
      files = "^renovate\\.json$";
      pass_filenames = false;
    };

    # These are enbaled on my server
    # docker-test-target = {
    #   enable = true;
    #   name = "docker build --target test";
    #   language = "system";
    #   pass_filenames = false;
    #   stages = [ "pre-commit" ];
    #   files = "^(src/|tests/|packaging/|pyproject\\.toml|uv\\.lock|Dockerfile|\\.dockerignore|\\.python-version)";
    #   entry = "docker buildx build --target test .";
    # };

    # version-bump-guard = {
    #   enable = true;
    #   name = "guard: version-relevant files changed without version bump";
    #   language = "system";
    #   pass_filenames = false;
    #   always_run = true;
    #   stages = [ "pre-commit" ];
    #   entry = "bash packaging/guard-version-bump.sh origin/main";
    # };

    # trivy-image-scan = {
    #   enable = true;
    #   name = "build + trivy image scan (CI replica)";
    #   language = "system";
    #   pass_filenames = false;
    #   files = "(^|/)pyproject\\.toml$";
    #   stages = [ "pre-push" ];
    #   entry = ''
    #     sh -euc 'sbom="$(mktemp)"
    #     docker buildx build --pull --platform linux/amd64 \
    #       --target runtime \
    #       --load -t local/runner-ci-scan:latest .
    #     trivy image --format cyclonedx --output "$sbom" local/runner-ci-scan:latest
    #     trivy sbom --exit-code 1 --ignore-unfixed \
    #       --severity CRITICAL,HIGH \
    #       --ignorefile packaging/.trivyignore "$sbom"'
    #   '';
    # };
  };

  dotenv.enable = false;
  dotenv.disableHint = true;

  env.LC_ALL = "C.UTF-8";
  env.LANG = "C.UTF-8";

  scripts.bump-pins.exec = ''
      set -euo pipefail
      secretspec run -- updatecli pipeline apply --config .config/updatecli.d/
    '';

  scripts.bump-semver.exec = ''
    set -euo pipefail
    cz bump --version-files-only --allow-no-commit --yes
  '';

  scripts.waow.exec = ''
    set -euo pipefail
    git add .
    bump-pins
    bump-semver
    git commit -am "$*"
    git push
  '';
#  enterShell = ''
#    export DOCKER_HOST="unix://$XDG_RUNTIME_DIR/docker.sock"
#  '';

#  processes.dockerd.exec = "dockerd-rootless";
}
