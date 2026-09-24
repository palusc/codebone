# typed: false
# frozen_string_literal: true

class Codebone < Formula
  desc "Invisible menubar assistant indexing live codebase structure on Apple Silicon"
  homepage "https://github.com/palusc/codebone"
  url "https://github.com/palusc/codebone/releases/download/v1.3.9/codebone-macos-arm64.zip"
  sha256 "a5ca3af4a7efbce2e4f5f1596e95efeffaaf191bb7b5dfa406b8dca3c8dc9411"
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
