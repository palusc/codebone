# typed: false
# frozen_string_literal: true

class Codebone < Formula
  desc "Invisible menubar assistant indexing live codebase structure on Apple Silicon"
  homepage "https://github.com/palusc/codebone"
  url "https://github.com/palusc/codebone/releases/download/v1.2.1/codebone-macos-arm64.zip"
  sha256 "dac3276f1320143ccd616ada03eed9c6bc72f0cf407af6e01937e6451b085965"
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
    EOS
  end

  test do
    assert_predicate prefix/"codebone.app/Contents/MacOS/codebone", :exist?
  end
end
