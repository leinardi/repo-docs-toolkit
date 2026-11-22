package main

import (
	"os"

	"github.com/spf13/cobra"
)

//go:generate go run ../../internal/gen -out ../../docs/reference.md

// Links shown in error messages.
const docsBase = "https://github.com/example/svc/blob/main/docs/"

var addr string

func main() {
	root := &cobra.Command{Use: "svc"}
	root.Flags().StringVar(&addr, "listen", ":8080", "address to listen on")
	root.PersistentFlags().Bool("verbose", false, "log more")
	_ = os.Getenv("SVC_TOKEN")
	_ = os.Getenv("SVC_DEBUG")
	_ = docsBase + "troubleshooting.md#busy"
	_ = root.Execute()
}
