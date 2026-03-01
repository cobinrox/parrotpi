class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
        this.port.onmessage = (e) => {
            this.buffer.push(new Float32Array(e.data));
        };
    }

    process(inputs, outputs, parameters) {
        const output = outputs[0];
        if (this.buffer.length > 0) {
            const chunk = this.buffer.shift();
            output[0].set(chunk.subarray(0, output[0].length));
        }
        return true;
    }
}
registerProcessor("pcm-processor", PCMProcessor);
