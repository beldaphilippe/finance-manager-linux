let
  pkgs = import <nixpkgs> {};
in pkgs.mkShell {
  packages = with pkgs; [
    gnupg
    pinentry-curses
    (python3.withPackages (python-pkgs: with python-pkgs; [
      flask
      google-auth
      google-auth-oauthlib
      google-api-python-client
      pycrypto
    ]))
  ];
}
