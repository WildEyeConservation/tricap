// The client control code is more extensive so as to reduce the total number of requests going
//  to the server, so as to reduce latency issues over 3G

// Create a namespace if not existing
var tricap = tricap || {};

// Code here will be linted with JSHint.
/* jshint ignore:start */
var numCams = {{num_cams}};
var imgTooOldCount = {{img_too_old_count}};
var camRefreshRate = {{refresh_rate}}
var stateRefreshRate = {{refresh_rate}}
// Code here will be ignored by JSHint.
/* jshint ignore:end */

// TODO Need to read the state of the cams before displaying, to update the images

// Constants go first (declared without a var}
tricap.BUTTON_CODES = Object.freeze({
    START: 0,
    STOP: 1,
    TEST: 2,
    RESET: 3,
    STARTSTOP: 4
});

tricap.CAPTURE_STATES = Object.freeze({
    STARTED: 0,
    STOPPED: 1
});

function camImgController() {
    this.imgId = 0;
    this.lastRequestId = -1;
    this.oldImgCount = 0;
}

camImgControllers = [];

// Then function declarations (i.e. function addTwoNumbers(a, b){ return a+b;};) so that hoisting
// is obvious

// Then function expressions (i.e. var a = function(a,b){return a+b;};). Note that the var a is
// hoisted as var a = undefined. So watch out.

var buttonClick = function(buttonCode){

    if (buttonCode === tricap.BUTTON_CODES.START || buttonCode === tricap.BUTTON_CODES.STOP ||
        buttonCode === tricap.BUTTON_CODES.STARTSTOP || tricap.BUTTON_CODES.TEST){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode }, buttonClickFollowUp);
    } else if (buttonCode === tricap.BUTTON_CODES.RESET){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode },
                  function(){location.reload(); return false;});
    }
    return false;
};

var buttonClickFollowUp = function (data) {
    if (data.hasOwnProperty('capture_state')){
        if (data.capture_state === tricap.CAPTURE_STATES.STARTED){
            $('#btn_startstop').innerHTML = 'STOP';
        } else {
            $('#btn_startstop').innerHTML = 'START';
        }
    }
    return false;
};

var refreshCamImages = function(){
    for (index = 0; index < camImgControllers.length; index++){
        if (camImgControllers[index].imgId !== camImgControllers[index].lastRequestId){
            var cam_img_url = $SCRIPT_ROOT + '/cam_img'+index+camImgControllers[index].imgId;
            $('#img_cam'+index).attr('src', cam_img_url);
            $('#alt_cam'+index).removeClass('alert-tricap-grey alert-tricap-red');
            $('#alt_cam'+index).addClass('alert-tricap-blue');
        } else {
            camImgControllers[index].oldImgCount = camImgControllers[index].oldImgCount + 1;
            if (camImgControllers[index].oldImgCount < imgTooOldCount){
                $('#alt_cam'+index).removeClass('alert-tricap-blue alert-tricap-red');
                $('#alt_cam'+index).addClass('alert-tricap-grey');
            } else {
                $('#alt_cam'+index).removeClass('alert-tricap-blue alert-tricap-grey');
                $('#alt_cam'+index).addClass('alert-tricap-red');
            }
        }
    }
    return false;
};

var requestStateData = function(data){
    return false;
};

// All of the following code will only run when the page is ready
//  (the $() is short for $(document).ready())
$(function(){
    //setup the cam image counter
    for (var index = 0; index < numCams; index++){
        camImgControllers.push(new camImgController());
    }

    // Set the specific button functions
    $("#btn_startstop").on('click', function(event){buttonClick(tricap.BUTTON_CODES.STARTSTOP);});
    $("#a_test").on('click', function(event){buttonClick(tricap.BUTTON_CODES.TEST);});
    $("#a_reset").on('click', function(event){buttonClick(tricap.BUTTON_CODES.RESET);});
    $("#img_cam_left").error(function(event){console.log('Error');});

    // Set the interval functions
    setInterval(refreshCamImages, camRefreshRate);
    setInterval(requestStateData, stateRefreshRate);
});
