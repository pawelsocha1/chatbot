import * as OBC from 'https://cdn.jsdelivr.net/npm/@thatopen/components/+esm';
import * as FRAGS from 'https://cdn.jsdelivr.net/npm/@thatopen/fragments/+esm';

const container = document.getElementById("container");

const components = new OBC.Components();
const worlds = components.get(OBC.Worlds);

const world = worlds.create(
  OBC.SimpleScene,
  OBC.SimpleCamera,
  OBC.SimpleRenderer
);

world.scene = new OBC.SimpleScene(components);
world.renderer = new OBC.SimpleRenderer(components, container);
world.camera = new OBC.SimpleCamera(components);

components.init();

world.camera.controls.setLookAt(12, 6, 8, 0, 0, -10);
world.scene.setup();

const grids = components.get(OBC.Grids);
grids.create(world);

let fragments;
let serializer;
let currentModel = null;

async function initializeFragments() {
    try {
        serializer = new FRAGS.IfcImporter();
        serializer.wasm = { 
            absolute: true, 
            path: "https://unpkg.com/web-ifc@0.0.68/" 
        };

        const workerUrl = "https://thatopen.github.io/engine_fragment/resources/worker.mjs";
        const fetchedWorker = await fetch(workerUrl);
        const workerText = await fetchedWorker.text();
        const workerFile = new File([new Blob([workerText])], "worker.mjs", {
            type: "text/javascript",
        });
        const url = URL.createObjectURL(workerFile);
        
        fragments = new FRAGS.FragmentsModels(url);
        world.camera.controls.addEventListener("rest", () => fragments.update(true));
        world.camera.controls.addEventListener("update", () => fragments.update());

        console.log('Fragments and IFC Importer initialized successfully');
        
        await loadDefaultModel();
        
    } catch (error) {
        console.error('Error initializing Fragments:', error);
    }
}

async function loadDefaultModel() {
    try {
        console.log('Loading default IFC model...');
        const response = await fetch('/default-model.ifc');
        if (!response.ok) {
            throw new Error(`Failed to fetch default model: ${response.status}`);
        }
        
        const ifcBuffer = await response.arrayBuffer();
        const ifcBytes = new Uint8Array(ifcBuffer);
        
        console.log('Converting IFC to fragments...');
        const fragmentBytes = await serializer.process({ bytes: ifcBytes });
        
        console.log('Loading fragments model...');
        const model = await fragments.load(fragmentBytes, { modelId: "default-model" });
        model.useCamera(world.camera.three);
        world.scene.three.add(model.object);
        
        currentModel = model;
        
        await fragments.update(true);
        
        console.log('Default IFC model loaded successfully');
        
    } catch (error) {
        console.error('Error loading default model:', error);
        alert('Failed to load default IFC model: ' + error.message);
    }
}

async function loadIfcModelFromUrl(url) {
    try {
        console.log('Loading IFC model from URL:', url);
        
        if (currentModel) {
            await fragments.disposeModel("uploaded-model");
            currentModel = null;
        }
        
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to fetch model: ${response.status}`);
        }
        
        const ifcBuffer = await response.arrayBuffer();
        const ifcBytes = new Uint8Array(ifcBuffer);
        
        console.log('Converting IFC to fragments...');
        const fragmentBytes = await serializer.process({ bytes: ifcBytes });
        
        console.log('Loading fragments model...');
        const model = await fragments.load(fragmentBytes, { modelId: "uploaded-model" });
        model.useCamera(world.camera.three);
        world.scene.three.add(model.object);
        
        currentModel = model;
        
        await fragments.update(true);
        
        console.log('IFC model loaded successfully from URL:', url);
        
    } catch (error) {
        console.error('Error loading IFC model from URL:', error);
        alert('Failed to load model in viewer: ' + error.message);
    }
}

window.viewerLoadModel = loadIfcModelFromUrl;
function setupQueryInterface() {
    const queryInput = document.getElementById('queryInput');
    const askButton = document.getElementById('askButton');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const responseArea = document.getElementById('responseArea');

    if (askButton && queryInput) {
        askButton.addEventListener('click', async () => {
            const query = queryInput.value.trim();
            
            if (!query) {
                alert('Proszę wprowadzić pytanie');
                return;
            }

            if (loadingIndicator) loadingIndicator.style.display = 'block';
            if (responseArea) responseArea.innerHTML = '';

            try {
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question: query
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                
                if (responseArea) {
                    responseArea.innerHTML = `
                        <div class="alert alert-info">
                            <strong>Odpowiedź:</strong> ${result.answer}
                        </div>
                    `;
                }

            } catch (error) {
                console.error('Query error:', error);
                if (responseArea) {
                    responseArea.innerHTML = `
                        <div class="alert alert-danger">
                            Błąd podczas przetwarzania zapytania: ${error.message}
                        </div>
                    `;
                }
            } finally {
                if (loadingIndicator) loadingIndicator.style.display = 'none';
            }
        });

        queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                askButton.click();
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', async function() {
    setupQueryInterface();
    
    await initializeFragments();
    
    console.log('IFC Viewer and UI initialized successfully');
}); 