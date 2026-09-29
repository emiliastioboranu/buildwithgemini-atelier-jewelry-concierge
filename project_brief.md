# My agent: Atelier Jewelry Concierge

One-liner: A conversational jewelry shop assistant that helps customers search a curated jewelry catalog, receive personalized recommendations based on style and material preferences, and save favorite pieces.

Tool coverage:
- Memory: Remembers customer preferences (preferred metals e.g. 18k Gold/Sterling Silver, gemstone preferences, ring sizes, budget range) and favorite items.
- Tools: `search_jewelry` (searches catalog by category, material, or price), `save_favorite` (saves a jewelry item to customer favorites), `get_favorites` (retrieves saved items).
- Catalog/UI: A curated catalog of rings, necklaces, earrings, and bracelets rendered as A2UI product cards and tables.
- Image gen: Generates visual previews or custom styling mockups of jewelry items using `gemini-3.1-flash-lite-image`.
- Sandbox: Simple budget calculations and discount/tax estimations.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): Custom image generation for bespoke jewelry design concepts, A2UI cards for interactive catalog browsing.
