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
    pkgs.git
    pkgs.hadolint
    pkgs.prek
  ];

  scripts.lint.exec = "prek run --all-files";

  # processes.app.exec = "docker compose up";

  enterShell = ''
    git --version
    uv --version
    hadolint --version
  '';

  enterTest = ''
    uv --version
    hadolint --version
  '';
}
