# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import subprocess
import time
import urllib.request
from typing import Any

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.cloud import firestore, storage
import google.oauth2.credentials

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback

PROJECT_ID = "qwiklabs-gcp-02-7f7d198e8c1e"
BUCKET_NAME = "atelier-jewelry-concierge-qwiklabs-gcp-02-7f7d198e8c1e"
MEMORY_BANK_ID = "900524212404355072"


def _get_db() -> firestore.Client:
    """Helper to initialize Firestore client with explicit hardcoded project ID."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], text=True
        ).strip()
        credentials = google.oauth2.credentials.Credentials(token)
        return firestore.Client(project=PROJECT_ID, credentials=credentials)
    except Exception:
        return firestore.Client(project=PROJECT_ID)


def _get_code_executor() -> AgentEngineSandboxCodeExecutor | None:
    """Load AgentEngineSandboxCodeExecutor using Reasoning Engine resource from deployment_metadata.json."""
    metadata_path = os.path.join(
        os.path.dirname(__file__), "..", "deployment_metadata.json"
    )
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                data = json.load(f)
            agent_engine_id = data.get("remote_agent_runtime_id")
            if agent_engine_id:
                return AgentEngineSandboxCodeExecutor(
                    agent_engine_resource_name=agent_engine_id
                )
        except Exception as e:
            print(f"Warning: Failed to load AgentEngineSandboxCodeExecutor: {e}")
    return None


def memory_bank_service_builder() -> VertexAiMemoryBankService:
    """Memory service builder for deployed container or Agent Runtime integration."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext) -> None:
    """Callback after each turn to extract and persist long-term memories to Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Warning: Failed to add session to memory: {e}")
    return None


def search_jewelry_catalog(
    category: str = "", query: str = "", max_price: float = 0.0
) -> list[dict[str, Any]]:
    """Search the jewelry product catalog in Firestore.

    Args:
        category: Filter by item category (e.g. 'Rings', 'Necklaces', 'Earrings', 'Bracelets').
        query: Keyword to search in name, material, gemstone, or description.
        max_price: Maximum price filter (0.0 means no limit).

    Returns:
        A list of matching jewelry items from the catalog.
    """
    db = _get_db()
    collection_ref = db.collection("jewelry_items")
    docs = collection_ref.stream()

    results = []
    category_clean = category.strip().lower()
    query_clean = query.strip().lower()

    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id

        if category_clean and item.get("category", "").lower() != category_clean:
            continue

        if max_price > 0.0 and float(item.get("price", 0.0)) > max_price:
            continue

        if query_clean:
            text = f"{item.get('name', '')} {item.get('material', '')} {item.get('gemstone', '')} {item.get('description', '')}".lower()
            if query_clean not in text:
                continue

        results.append(item)

    return results


def save_favorite(user_id: str, item_id: str) -> str:
    """Save a jewelry item to a customer's favorites list in Firestore.

    Args:
        user_id: The ID or name of the customer.
        item_id: The ID of the jewelry item to favorite (e.g. 'ring-001').

    Returns:
        A confirmation message.
    """
    db = _get_db()
    # Verify item exists
    item_doc = db.collection("jewelry_items").document(item_id).get()
    if not item_doc.exists:
        return f"Item '{item_id}' not found in the catalog."

    fav_ref = db.collection("user_favorites").document(user_id)
    fav_doc = fav_ref.get()

    favorites = []
    if fav_doc.exists:
        favorites = fav_doc.to_dict().get("items", [])

    if item_id not in favorites:
        favorites.append(item_id)
        fav_ref.set({"items": favorites}, merge=True)
        return f"Successfully saved item '{item_id}' ({item_doc.to_dict().get('name')}) to favorites for user '{user_id}'."
    else:
        return f"Item '{item_id}' is already in favorites for user '{user_id}'."


def get_favorites(user_id: str) -> list[dict[str, Any]]:
    """Retrieve all saved favorite jewelry items for a customer.

    Args:
        user_id: The ID or name of the customer.

    Returns:
        A list of jewelry item details that the customer has saved.
    """
    db = _get_db()
    fav_doc = db.collection("user_favorites").document(user_id).get()

    if not fav_doc.exists:
        return []

    item_ids = fav_doc.to_dict().get("items", [])
    favorites = []

    for item_id in item_ids:
        item_doc = db.collection("jewelry_items").document(item_id).get()
        if item_doc.exists:
            item = item_doc.to_dict()
            item["id"] = item_doc.id
            favorites.append(item)

    return favorites


def convert_eur_price(amount_eur: float) -> dict[str, Any]:
    """Convert a jewelry price in EUR to RON and USD using live exchange rates from ExchangeRate-API.

    Args:
        amount_eur: The price in EUR to convert.

    Returns:
        A dictionary containing converted amounts in USD and RON, exchange rates, and the rate update date, or error details if unavailable.
    """
    url = "https://open.er-api.com/v6/latest/EUR"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                return {"error": f"Failed to fetch exchange rates. HTTP status: {response.status}"}
            data = json.loads(response.read().decode("utf-8"))

        if data.get("result") != "success":
            return {"error": f"Exchange rate API returned error: {data.get('error-type', 'Unknown error')}"}

        rates = data.get("rates", {})
        usd_rate = rates.get("USD")
        ron_rate = rates.get("RON")
        rate_date = data.get("time_last_update_utc", "Unknown date")

        if usd_rate is None or ron_rate is None:
            return {"error": "Required exchange rates (USD, RON) were not returned by the API."}

        usd_amount = round(amount_eur * usd_rate, 2)
        ron_amount = round(amount_eur * ron_rate, 2)

        return {
            "amount_eur": amount_eur,
            "amount_usd": usd_amount,
            "amount_ron": ron_amount,
            "usd_rate": usd_rate,
            "ron_rate": ron_rate,
            "rate_date": rate_date,
        }
    except Exception as e:
        return {"error": f"Exchange rate service unavailable: {str(e)}"}


def generate_jewelry_image(
    tool_context: ToolContext, item_description: str, item_name: str = "jewelry_item"
) -> dict[str, Any]:
    """Generate a realistic image preview for a jewelry piece using gemini-3.1-flash-lite-image, save it as an artifact, and upload it to public Cloud Storage.

    Args:
        tool_context: ADK ToolContext injected automatically.
        item_description: Visual description of the jewelry item to generate (e.g. '18k yellow gold solitaire diamond ring on a black velvet cushion').
        item_name: Short identifier or name for the jewelry item (e.g. 'ring-001').

    Returns:
        A dictionary containing the public HTTPS URL of the generated image and status details.
    """
    try:
        genai_client = genai.Client(
            vertexai=True, project=PROJECT_ID, location="global"
        )
        prompt = (
            f"Professional studio product photography of luxury jewelry: {item_description}. "
            f"Elegant studio lighting, sharp focus, high luxury detail."
        )

        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break

        if not image_bytes:
            return {"error": "Failed to generate image bytes from the model response."}

        # Sanitize filename
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in item_name.lower()
        )
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"{safe_name}_{int(time.time())}.{ext}"

        # 1. Save artifact in ADK ToolContext (appears in Playground Artifacts panel)
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        res = tool_context.save_artifact(filename, artifact_part)
        if hasattr(res, "__await__"):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(res)
                else:
                    loop.run_until_complete(res)
            except Exception:
                pass

        # 2. Upload image to public GCS bucket
        try:
            token = subprocess.check_output(
                ["gcloud", "auth", "print-access-token"], text=True
            ).strip()
            credentials = google.oauth2.credentials.Credentials(token)
            storage_client = storage.Client(project=PROJECT_ID, credentials=credentials)
        except Exception:
            storage_client = storage.Client(project=PROJECT_ID)

        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "item_name": item_name,
            "filename": filename,
            "public_url": public_url,
            "message": f"Successfully generated image preview for '{item_name}' and published to public storage.",
        }
    except Exception as e:
        return {"error": f"Image generation failed: {str(e)}"}


# Build A2UI v0.8 system prompt
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Atelier Jewelry Concierge, an elegant and attentive AI personal shopping assistant. "
        "Help customers discover luxury jewelry from our catalog, search for pieces matching their preferred metal, gemstone, category, or budget, "
        "convert prices between EUR, USD, and RON using live exchange rates, "
        "generate visual image previews for jewelry items, "
        "calculate discounts, luxury taxes, or multi-item totals using Python code execution, "
        "and save their favorite items to their personal wishlist."
    ),
    workflow_description="Analyze the request, search or manipulate jewelry catalog items, and return structured UI cards when displaying items, recommendations, or catalog search results.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        search_jewelry_catalog,
        save_favorite,
        get_favorites,
        convert_eur_price,
        generate_jewelry_image,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
    code_executor=_get_code_executor(),
)

app = App(
    root_agent=root_agent,
    name="app",
)
