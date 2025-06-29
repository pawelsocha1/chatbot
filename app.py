import pickle
import faiss
import numpy as np
import ifcopenshell
import requests
import re

from flask import Flask, request, jsonify, send_from_directory
from sentence_transformers import SentenceTransformer

GEMINI_API_KEY = "AIzaSyDTlzt61gty98omZh63WQk3GLhHCqJo_4Q"

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return send_from_directory('.', 'index.html')

@app.route('/default-model.ifc', methods=['GET'])
def serve_default_ifc():
    filename = 'default.ifc'
    return send_from_directory('.', filename, mimetype='application/octet-stream')




def extract_ifc_chunks(ifc_path, chunk_size=10):
    ifc = ifcopenshell.open(ifc_path)
    element_types = [
        'IfcWall', 'IfcDoor', 'IfcWindow', 'IfcSlab',
        'IfcColumn', 'IfcBeam', 'IfcSpace', 'IfcBuildingStorey'
    ]
    chunks = []
    for etype in element_types:
        elements = ifc.by_type(etype)
        for i in range(0, len(elements), chunk_size):
            batch = elements[i:i+chunk_size]
            texts = []
            for el in batch:
                props = []
                for attr, val in el.get_info().items():
                    v = getattr(el, attr, None)
                    if v is not None and not isinstance(v, (list, dict)):
                        props.append(f"{attr}: {v}")
                texts.append(f"{etype} {el.GlobalId}\n" + "\n".join(props))
            chunks.append("\n---\n".join(texts))
    return chunks


def embed_chunks_local(chunks, model_name='all-MiniLM-L6-v2'):
    model     = SentenceTransformer(model_name)
    embeddings = model.encode(chunks, show_progress_bar=False)
    return embeddings


def build_faiss_index(embeddings, chunks, index_path):
    dim   = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings).astype('float32'))
    faiss.write_index(index, index_path)
    with open(f"{index_path}.chunks.pkl", 'wb') as f:
        pickle.dump(chunks, f)


def retrieve_similar_chunks(query, model, index_path, top_k=3):
    index = faiss.read_index(index_path)
    with open(f"{index_path}.chunks.pkl", 'rb') as f:
        chunks = pickle.load(f)
    q_emb = model.encode([query])
    _, I  = index.search(np.array(q_emb).astype('float32'), top_k)
    return [chunks[i] for i in I[0]]


def call_gemini_api(question, context_chunks, api_key):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.0-flash:generateContent"
        f"?key={api_key}"
    )
    prompt = (
        "Context:\n" +
        "\n\n".join(context_chunks) +
        f"\n\nQuestion: {question}\nAnswer:"
    )
    data = {"contents":[{"parts":[{"text": prompt}]}]}
    resp = requests.post(url, json=data)
    if resp.status_code == 200:
        js = resp.json()
        try:
            return js['candidates'][0]['content']['parts'][0]['text']
        except:
            return "Nie udało się sparsować odpowiedzi Gemini."
    else:
        return f"Gemini API error {resp.status_code}: {resp.text}"


def compute_surface_area(ifc_path: str, ifc_type: str) -> float:
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_PYTHON_OPENCASCADE, True)
    settings.set(settings.SEW_SHELLS, True)
    settings.set(settings.USE_BREP_DATA, True)

    model = ifcopenshell.open(ifc_path)
    total_area = 0.0

    for element in model.by_type(ifc_type):
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        faces = shape.geometry.faces

        for fi in range(0, len(faces), 3):
            i0, i1, i2 = faces[fi:fi+3]
            v0 = np.array(verts[3*i0:3*i0+3])
            v1 = np.array(verts[3*i1:3*i1+3])
            v2 = np.array(verts[3*i2:3*i2+3])
            tri_area = np.linalg.norm(np.cross(v1-v0, v2-v0)) * 0.5
            total_area += tri_area

    return total_area

def count_entities(ifc_path: str, ifc_type: str) -> int:
    ifc = ifcopenshell.open(ifc_path)
    return len(ifc.by_type(ifc_type))

def get_storey_info(ifc_path: str) -> tuple[int, list[str]]:
    ifc = ifcopenshell.open(ifc_path)
    storeys = ifc.by_type('IfcBuildingStorey')
    storey_names = []
    for storey in storeys:
        name = storey.Name if hasattr(storey, 'Name') and storey.Name else str(storey.Elevation)
        storey_names.append(name)
    return len(storeys), sorted(storey_names)

TYPE_MAP = {
    'ścian': 'IfcWall',
    'drzwi': 'IfcDoor',
    'okien': 'IfcWindow',
    'okna':  'IfcWindow',
    'słupów': 'IfcColumn',
    'belk':  'IfcBeam',
    'belek': 'IfcBeam',
    'stropów': 'IfcSlab',
    'stropow': 'IfcSlab',
    'przestrzeni': 'IfcSpace',
    'kondygnacji': 'IfcBuildingStorey',
    'walls': 'IfcWall',
    'wall': 'IfcWall',
    'doors': 'IfcDoor',
    'door': 'IfcDoor',
    'windows': 'IfcWindow',
    'window': 'IfcWindow',
    'columns': 'IfcColumn',
    'column': 'IfcColumn',
    'beams': 'IfcBeam',
    'beam': 'IfcBeam',
    'slabs': 'IfcSlab',
    'slab': 'IfcSlab',
    'spaces': 'IfcSpace',
    'space': 'IfcSpace',
    'storeys': 'IfcBuildingStorey',
    'storey': 'IfcBuildingStorey',
    'floors': 'IfcBuildingStorey',
    'floor': 'IfcBuildingStorey',
    'levels': 'IfcBuildingStorey',
    'level': 'IfcBuildingStorey'
}

def process_ifc_query(ifc_path: str, question: str) -> str:
    q = question.strip().lower()

    m1 = re.search(r"(how many|ile) (is |are |jest |mam )?(\w+)", q)
    if m1:
        key = m1.group(3)
        if key in TYPE_MAP:
            if 'storey' in key or 'floor' in key or 'level' in key or 'kondygnacji' in key or 'pięter' in key or 'piętro' in key:
                count, names = get_storey_info(ifc_path)
                if 'how many' in q.lower():
                    return f"The building has {count} storeys: {', '.join(names)}."
                else:
                    return f"Budynek ma {count} pięter: {', '.join(names)}."
            cnt = count_entities(ifc_path, TYPE_MAP[key])
            if 'how many' in q.lower():
                return f"There are {cnt} {key} in the model."
            return f"W modelu jest {cnt} {key}."

    m2 = re.search(r"powierzchni\w* (\w+)", q)
    if m2:
        key = m2.group(1)
        if key in TYPE_MAP:
            cls = TYPE_MAP[key]
            area = compute_surface_area(ifc_path, cls)
            return f"Powierzchnia wszystkich obiektów typu {key} wynosi {area:.2f} m²."
        else:
            return f"Nie znam typu '{key}' do obliczenia powierzchni."

    chunks     = extract_ifc_chunks(ifc_path)
    model      = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = embed_chunks_local(chunks)
    idx_path   = f"{ifc_path}.index"
    build_faiss_index(embeddings, chunks, idx_path)
    relevant   = retrieve_similar_chunks(question, model, idx_path, top_k=10)
    return call_gemini_api(question, relevant, GEMINI_API_KEY)
    
@app.route('/ask', methods=['POST'])
def web_ask():
    data = request.get_json(force=True)
    question = data.get('question','').strip()
    if not question:
        return jsonify({"error":"Brak question"}), 400
    
    ifc_path = 'default.ifc'

    try:
        answer = process_ifc_query(ifc_path, question)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
