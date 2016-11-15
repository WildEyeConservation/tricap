var numCams = {{num_cams}};

// TODO Need to read the state of the cams before displaying, to update the images

BUTTON_CODE_START = 0;
BUTTON_CODE_STOP = 1;
BUTTON_CODE_TEST = 2;
BUTTON_CODE_RESET = 3;

var buttonClickFollowUp = function () {
    console.log("Button Click Follow Up");
    return false;
}

var handleButtonClick = function(buttonCode){

    if (buttonCode === BUTTON_CODE_START || buttonCode === BUTTON_CODE_STOP){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode }, buttonClickFollowUp);
    } else if (buttonCode === BUTTON_CODE_RESET){
        console.log('Reset Pressed');
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode },
            function(){location.reload(); return false;});
    }

    return false;

}

$(function () {
    var buttonClick = function (e) {
    console.log("Start Clicked");
    handleButtonClick(BUTTON_CODE_START);
    return false;
    };
    document.getElementById("btn_start").onclick = buttonClick
});

$(function () {
    var buttonClick = function (e) {
    console.log("Stop Clicked");
    handleButtonClick(BUTTON_CODE_STOP);
    return false;
    };
    document.getElementById("btn_stop").onclick = buttonClick
});

$(function () {
    var buttonClick = function (e) {
    console.log("Reset Clicked");
    handleButtonClick(BUTTON_CODE_RESET);
    return false;
    };
    document.getElementById("btn_reset").onclick = buttonClick
});


var camImageCheckFollowUp = function(data){
    var img = document.getElementById('img_cam'+data.cam_num);
    if (data.new_image === true){
        img.src = '/cam_img' + data.cam_num + '?'+ new Date().getTime();
        img.style.border = '5px solid blue';
    }
    else {
        img.style.border = '5px solid grey';
    }

    //TODO: Make the border red on a bad cam state

    var p_cam_state = document.getElementById('p_cam_state_'+data.cam_num);
    p_cam_state.innerHTML = 'Camera state: ' + data.cam_state;
}

$(function () {
    var imgCheckupFunc = function(){
        for (index = 0; index < numCams; index++){
            $.getJSON($SCRIPT_ROOT + '/_check_cam_image'+index, {}, camImageCheckFollowUp)
        }
        return false;
    };
    setInterval(imgCheckupFunc, 1000);
});

var altiCheckFollowup = function(data){
    var pAltiState = document.getElementById('p_alti_state');
    pAltiState.innerHTML = 'Altimeter state : ' + data.alti_state;

    var pAltiMeasurement = document.getElementById('p_alti_measurement');
    pAltiMeasurement.innerHTML = 'Altimeter measurement : ' + data.alti_measurement;
}

$(function () {
    var altiCheckup = function(){
        $.getJSON($SCRIPT_ROOT + '/_get_alti_data', {}, altiCheckFollowup)
        return false;
    };
    setInterval(altiCheckup, 1000);
});
