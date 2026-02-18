/*
Tdarr_Plugin_vsAIQ.js
Author: Gemini
Version: 1.5.0
Description: A Tdarr transcode plugin that uses the intelligent quality (CRF) settings from VideoSentinel.
*/

const details = () => {
    return {
        id: "Tdarr_Plugin_vsAIQ",
        Stage: "Pre-processing",
        Name: "VideoSentinel - Intelligent Quality Encoding",
        Type: "Video",
        Operation: "Transcode",
        Description: `
[Contains built-in filter] This plugin uses the intelligent quality (CRF) settings from the VideoSentinel project.
It dynamically calculates the best CRF value for transcoding based on the source video's bitrate, resolution, and framerate.
This version includes a quality modifier to easily tune the output quality and an option for 10-bit output.
`,
        Version: "1.5.0",
        Tags: "pre-processing,transcode,video-sentinel,cpu,dynamic crf,ffmpeg,10bit",
        Inputs: [{
            name: "target_codec",
            type: 'string',
            defaultValue: 'hevc',
            inputUI: {
                type: 'dropdown',
                options: ['hevc', 'h264', 'av1'],
            },
            tooltip: `Specify the target video codec.
- hevc (libx265)
- h264 (libx264)
- av1 (libaom-av1)
Default: hevc`
        }, {
            name: "target_preset",
            type: 'string',
            defaultValue: 'medium',
            inputUI: {
                type: 'dropdown',
                options: ['fast', 'medium', 'slow', 'veryslow'],
            },
            tooltip: `Specify the encoder preset (speed vs. quality tradeoff).
Default: medium`
        }, {
            name: "audio_codec",
            type: 'string',
            defaultValue: 'aac',
            inputUI: {
                type: 'dropdown',
                options: ['copy', 'aac', 'ac3', 'eac3', 'opus'],
            },
            tooltip: `Specify the audio codec. Use 'copy' to keep the original audio stream without re-encoding.
Default: aac`
        }, {
            name: "quality_modifier",
            type: 'string',
            defaultValue: '0',
            inputUI: {
                type: 'text',
            },
            tooltip: `Adjust the calculated CRF value to tune quality.
A negative number increases quality (e.g., -2 for higher quality).
A positive number decreases quality (e.g., 2 for smaller files).
Default is 0.`
        }, {
            name: "enable_10bit",
            type: 'boolean',
            defaultValue: false,
            inputUI: {
                type: 'dropdown',
                options: [
                    'false',
                    'true',
                ],
            },
            tooltip: `Specify if output file should be 10bit. Default is false.
Set to 'true' to enable 10-bit color depth for better quality, especially with HEVC.`
        }, ],
    };
};

const plugin = (file, librarySettings, inputs, otherArguments) => {
    const lib = require('../methods/lib')();
    // eslint-disable-next-line no-param-reassign
    inputs = lib.loadDefaultValues(inputs, details);

    const response = {
        processFile: false,
        preset: '',
        container: ".mp4",
        handBrakeMode: false,
        FFmpegMode: true,
        reQueueAfter: true,
        infoLog: "",
    };

    // 1. FILE SANITY CHECKS
    if (file.fileMedium !== "video") {
        response.infoLog += "File is not a video file. Skipping.\n";
        return response;
    }
    if (!file.ffProbeData || !file.ffProbeData.streams || !Array.isArray(file.ffProbeData.streams)) {
        response.infoLog += "ffProbe data or streams are missing. File may need a re-scan. Skipping.\n";
        return response;
    }

    // 2. FIND VIDEO STREAM
    const videoStream = file.ffProbeData.streams.find(stream => stream && stream.codec_type === 'video' && (stream.codec_name !== 'mjpeg' && stream.codec_name !== 'png'));
    if (!videoStream) {
        response.infoLog += "No valid video stream found in the file. Skipping.\n";
        return response;
    }

    // 3. BUILT-IN FILTER: CHECK CURRENT CODEC
    const currentCodec = videoStream.codec_name;
    const targetCodec = inputs.target_codec;
    if ((targetCodec === 'hevc' && currentCodec === 'hevc') ||
        (targetCodec === 'h264' && currentCodec === 'h264') ||
        (targetCodec === 'av1' && currentCodec === 'av1')) {
        response.infoLog += `File is already in the target codec (${currentCodec}). Skipping.\n`;
        return response;
    }

    // 4. GATHER VIDEO INFO (DEFENSIVELY)
    const videoInfo = {};
    if (!videoStream.width || !videoStream.height) {
        response.infoLog += "Video stream is missing width or height. Skipping.\n";
        return response;
    }
    videoInfo.width = videoStream.width;
    videoInfo.height = videoStream.height;

    if (file.meta && file.meta.Duration) {
        videoInfo.duration = parseFloat(file.meta.Duration);
    }
    if (!videoInfo.duration && file.ffProbeData && file.ffProbeData.format) {
        videoInfo.duration = parseFloat(file.ffProbeData.format.duration);
    }
    if (!videoInfo.duration) {
        response.infoLog += "File is missing duration metadata. Skipping.\n";
        return response;
    }

    if (file.meta && file.meta.BitRate) {
        videoInfo.bitrate = parseInt(file.meta.BitRate, 10);
    } else if (file.file_size && videoInfo.duration > 0) {
        videoInfo.bitrate = (file.file_size * 8) / videoInfo.duration;
        response.infoLog += "Used file size and duration to calculate bitrate.\n";
    }
    if (!videoInfo.bitrate) {
        response.infoLog += "Could not determine bitrate. Skipping.\n";
        return response;
    }

    videoInfo.fps = 30; // Default
    if (videoStream.r_frame_rate) {
        try {
            const parts = String(videoStream.r_frame_rate).split('/');
            if (parts.length === 2 && parseFloat(parts[1]) !== 0) {
                videoInfo.fps = parseFloat(parts[0]) / parseFloat(parts[1]);
            } else if (parts.length === 1) {
                videoInfo.fps = parseFloat(parts[0]);
            }
        } catch (e) {
            response.infoLog += `Could not parse framerate ('${videoStream.r_frame_rate}'), using default 30fps.\n`;
        }
    }

    // 5. CALCULATE CRF & APPLY MODIFIER
    const calculateOptimalCRF = (info, codec) => {
        const pixels = info.width * info.height;
        const fps = info.fps > 0 ? info.fps : 30;
        const bpp = info.bitrate / (pixels * fps);
        let crf = 23;
        response.infoLog += `Source Info: ${info.width}x${info.height} @ ${info.fps.toFixed(2)}fps, Bitrate: ${Math.round(info.bitrate / 1000)} kbps\n`;
        response.infoLog += `Calculated BPP: ${bpp.toFixed(4)}\n`;
        const codec_lower = codec.toLowerCase();
        if (codec_lower === 'hevc' || codec_lower === 'h265') {
            if (bpp > 0.25) crf = 18; else if (bpp > 0.15) crf = 20; else if (bpp > 0.10) crf = 22; else if (bpp > 0.07) crf = 23; else if (bpp > 0.05) crf = 25; else crf = 28;
        } else if (codec_lower === 'av1') {
            if (bpp > 0.25) crf = 20; else if (bpp > 0.15) crf = 24; else if (bpp > 0.10) crf = 28; else if (bpp > 0.07) crf = 30; else crf = 32;
        } else { // H.264
            if (bpp > 0.25) crf = 16; else if (bpp > 0.15) crf = 18; else if (bpp > 0.10) crf = 20; else if (bpp > 0.07) crf = 21; else if (bpp > 0.05) crf = 23; else crf = 26;
        }
        return crf;
    };

    let optimalCRF = calculateOptimalCRF(videoInfo, targetCodec);
    response.infoLog += `Base CRF calculated: ${optimalCRF}\n`;

    const qualityModifier = parseInt(inputs.quality_modifier, 10);
    if (!isNaN(qualityModifier) && qualityModifier !== 0) {
        optimalCRF += qualityModifier;
        response.infoLog += `Applying quality modifier of ${inputs.quality_modifier}. Final CRF: ${optimalCRF}\n`;
    }

    // 6. BUILD FFMPEG PRESET
    const codecMap = { 'h264': 'libx264', 'hevc': 'libx265', 'av1': 'libaom-av1' };
    const ffmpegCodec = codecMap[targetCodec];
    let extraArguments = '';

    const vf_filters = [];
    if (targetCodec.toLowerCase() === 'hevc') {
        vf_filters.push('scale=trunc(iw/2)*2:trunc(ih/2)*2');
    }
    if (vf_filters.length > 0) {
        extraArguments += ` -vf ${vf_filters.join(',')}`;
    }
    if (targetCodec.toLowerCase() === 'hevc') {
        extraArguments += ' -tag:v hvc1';
    }
    
    // Add 10-bit pixel format if enabled and target codec supports it well (HEVC, AV1)
    if (inputs.enable_10bit === true && (targetCodec.toLowerCase() === 'hevc' || targetCodec.toLowerCase() === 'av1')) {
        extraArguments += ' -pix_fmt p010le';
        response.infoLog += 'Enabled 10-bit pixel format (p010le).\n';
    } else if (inputs.enable_10bit === true && targetCodec.toLowerCase() === 'h264') {
        // Warn if user enables 10bit for H264, as libx264 10bit support isn't as common/efficient
        response.infoLog += 'Warning: 10-bit output for H.264 is enabled, but typically more efficient for HEVC/AV1.\n';
        extraArguments += ' -pix_fmt yuv420p10le'; // libx264 10bit usually prefers yuv420p10le
    }


    extraArguments += ` -c:s copy`;
    extraArguments += ` -max_muxing_queue_size 9999`;

    response.preset = `,-map 0 -c:v ${ffmpegCodec} -preset ${inputs.target_preset} -crf ${optimalCRF} -c:a ${inputs.audio_codec} ${extraArguments}`;
    response.processFile = true;
    response.infoLog += `File is not ${targetCodec}. Transcoding with preset: ${response.preset}\n`;

    return response;
};

module.exports.details = details;
module.exports.plugin = plugin;
