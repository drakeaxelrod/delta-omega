{
  description = "Delta Omega split keyboard — ZMK firmware & config";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Zephyr SDK + Python environment for ZMK builds
    zephyr = {
      url = "github:zmkfirmware/zephyr/v4.1.0+zmk-fixes";
      flake = false;
    };
    zephyr-nix = {
      url = "github:urob/zephyr-nix";
      inputs.zephyr.follows = "zephyr";
      # Don't follow nixpkgs — zephyr-nix needs python310 which newer nixpkgs dropped
    };
  };

  outputs = { self, nixpkgs, flake-utils, zephyr-nix, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          # nrf-command-line-tools / segger-jlink are proprietary
          config.allowUnfreePredicate = pkg:
            builtins.elem (pkgs.lib.getName pkg) [ "nrf-command-line-tools" "segger-jlink" ];
          config.permittedInsecurePackages = [ "segger-jlink-qt4-874" ];
          config.segger-jlink.acceptLicense = true;
        };
        zephyr = zephyr-nix.packages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Zephyr / ZMK
            zephyr.pythonEnv
            (zephyr.sdk.override { targets = [ "arm-zephyr-eabi" ]; })
            cmake
            dtc
            ninja
            protobuf
            python3Packages.protobuf

            # Tools
            just
            picocom
            openocd
            nrf-command-line-tools
          ];

          env = {
            PYTHONPATH = "${zephyr.pythonEnv}/${zephyr.pythonEnv.sitePackages}";
          };

          shellHook = ''
            echo "Delta Omega keyboard — run 'just' to see available commands"
          '';
        };
      }
    );
}
