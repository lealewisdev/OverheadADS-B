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
  ];

  env.LC_ALL = "C.UTF-8";
  env.LANG = "C.UTF-8";

  scripts.lint.exec = "prek run --all-files";

  enterShell = ''
    export DOCKER_HOST="unix://$XDG_RUNTIME_DIR/docker.sock"
  '';

  processes.dockerd.exec = "dockerd-rootless";

  /*
  scripts.build-image.exec = ''
    set -euo pipefail
    docker buildx inspect local-builder >/dev/null 2>&1 || \
      docker buildx create --name local-builder --use
    docker buildx build \
      --pull \
      --platform linux/amd64 \
      --target runtime \
      --load \
      -t overheadadsb:local \
      .
  '';

  scripts.scan-image.exec = ''
    set -euo pipefail
    trivy image \
      --format cyclonedx \
      --output sbom.cdx.json \
      overheadadsb:local
    trivy sbom \
      --exit-code 1 \
      --ignore-unfixed \
      --severity CRITICAL,HIGH \
      --ignorefile packaging/.trivyignore \
      sbom.cdx.json
  '';
*/
}
