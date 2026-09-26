# typed: false
# frozen_string_literal: true

class Codebone < Formula
  desc "Invisible menubar assistant indexing live codebase structure on Apple Silicon"
  homepage "https://github.com/palusc/codebone"
  url "https://github.com/palusc/codebone/releases/download/v1.7.0/codebone-macos-arm64.zip"
  sha256 "e6511dc9ddd0fa69c213b33d77925f90601cf70d2b2121b14bd734120bf8afa6"
  license "MIT"
  head "https://github.com/palusc/codebone.git", branch: "main"

  depends_on arch: :arm64
  depends_on :macos

  def install
    prefix.install "codebone.app"
  end

  def caveats
    <<~EOS
      To start codebone, launch the application from:
        #{opt_prefix}/codebone.app
      
      Or link it directly into your /Applications directory:
        ln -sf "#{opt_prefix}/codebone.app" /Applications/codebone.app

      To remove codebone completely (app, data, models, MCP entries), use
      the menu bar icon > Settings > Uninstall codebone...
    EOS
  end

  test do
    assert_predicate prefix/"codebone.app/Contents/MacOS/codebone", :exist?
  end
end
