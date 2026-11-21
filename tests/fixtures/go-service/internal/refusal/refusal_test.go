package refusal

import (
	"os"
	"testing"
)

func TestDocsListEveryRefusal(t *testing.T) {
	if _, err := os.ReadFile("../../docs/troubleshooting.md"); err != nil {
		t.Fatal(err)
	}
}
