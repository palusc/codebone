# typed: false
# frozen_string_literal: true

class Codebone < Formula
  desc "Invisible menubar assistant indexing live codebase structure on Apple Silicon"
  homepage "https://github.com/palusc/codebone"
  url "https://github.com/palusc/codebone/releases/download/v1.0.0/codebone-macos-arm64-v1.0.0.zip"
  sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" # Update on release
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
