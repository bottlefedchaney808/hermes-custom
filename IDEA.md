A plugin layer that adds custom tools, persistent memory, and skill packs to Hermes agents without forking the core runtime.

- Ship a registry so new tools register via config and typed schemas
- Add session-spanning vector memory with retrieval and decay
- Bundle three skill packs: coding, research, and data analysis
- Provide a loader, example plugins, and a small eval harness for tool use and recall
- Keep the expansion drop-in so existing Hermes prompts and loops stay unchanged
