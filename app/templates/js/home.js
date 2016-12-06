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
var timeOutPeriod = {{timeout_period}}
// Code here will be ignored by JSHint.
/* jshint ignore:end */

// TODO Need to read the state of the cams before displaying, to update the images

// Constants go first (declared without a var}

tricap.GLOBAL_STATES = Object.freeze({
    INITIALISED: 0,
    CAPTURING: 1,
    ERROR: 2
});

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

//ALTIMETER_STATE = Enum("AltiState", ["NOT_CONNECTED", "CONNECTED", "MEASURING", "ERROR"])
tricap.ALTI_STATES = Object.freeze({
    NOT_CONNECTED: 0,
    CONNECTED: 1,
    MEASURING: 2,
    ERROR: 3
});

//Object Constructors

function camImgController() {
    this.imgId = 0;
    this.lastRequestId = -1;
    this.oldImgCount = 0;
}

//Globals

var camImgControllers = [];
var globalState = tricap.GLOBAL_STATES.INITIALISED;
var timeoutFunc;

// Then function declarations (i.e. function addTwoNumbers(a, b){ return a+b;};) so that hoisting
// is obvious
function changeStateColour(elem_id, target_colour){

    //Check if its an alert (i.e. a div) or a button (i.e. an a)
    var elem = $('#'+elem_id);

    var pre;
    if (elem.is('div') === true){
        pre='alert-';
    } else if (elem.is('a') === true){
        pre='btn-';
    }

    if (target_colour === 'red'){
        elem.removeClass(pre+'tricap-green '+pre+'tricap-orange');
        elem.addClass(pre+'tricap-red');
    } else if (target_colour === 'green'){
        elem.removeClass(pre+'tricap-red '+pre+'tricap-orange');
        elem.addClass(pre+'tricap-green');
    } else if (target_colour === 'orange'){
        elem.removeClass(pre+'tricap-green '+pre+'tricap-red');
        elem.addClass(pre+'tricap-orange');
    }
}

function changeTimeColour(elem_id, target_colour){

    //Check if its an alert (i.e. a div) or a button (i.e. an a)
    var elem = $('#'+elem_id);

    var pre;
    if (elem.is('div') === true){
        pre='alert-';
    } else if (elem.is('a') === true){
        pre='btn-';
    }

    if (target_colour === 'grey'){
        elem.removeClass(pre+'tricap-blue '+pre+'tricap-red');
        elem.addClass(pre+'tricap-grey');
    } else if (target_colour === 'blue'){
        elem.removeClass(pre+'tricap-grey '+pre+'tricap-red');
        elem.addClass(pre+'tricap-blue');
    } else if (target_colour === 'red'){
        elem.removeClass(pre+'tricap-blue '+pre+'tricap-grey');
        elem.addClass(pre+'tricap-red');
    }
}

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
            changeTimeColour('alt_cam', 'blue');
        } else {
            camImgControllers[index].oldImgCount = camImgControllers[index].oldImgCount + 1;
            if (camImgControllers[index].oldImgCount < imgTooOldCount){
                changeTimeColour('alt_cam', 'grey');
            } else {
                changeTimeColour('alt_cam', 'red');
            }
        }
    }
    return false;
};

var updateAlti = function(data){
    $('#h_alti').html('Altitude: ' + data.measurement + ' m');

    if (data.state === tricap.ALTI_STATES.CONNECTED) {
        changeStateColour('alt_alti', 'orange');
        changeStateColour('btn_alti', 'orange');
    } else if (data.state === tricap.ALTI_STATES.MEASURING) {
        changeStateColour('alt_alti', 'green');
        changeStateColour('btn_alti', 'green');
    } else {
        changeStateColour('alt_alti', 'red');
        changeStateColour('btn_alti', 'red');
    }

    return false;
};

var requestStateData = function(data){
    $.getJSON($SCRIPT_ROOT + '/_get_state_data', {},
              function(data){
                  updateAlti(data.alti);

                  //Reset the timeout period
                  clearTimeout(timeoutFunc);
                  timeoutFunc = setTimeout(showNoResponseMessage, timeOutPeriod);
                  return false;
              });
    return false;
};

var showNoResponseMessage = function(){
    // TODO Implement an observer pattern for the globalState

    $('#h_main_status').html('No Response From Server');

    globalState = tricap.GLOBAL_STATES.ERROR;
    changeStateColour('alt_main_status', 'red');
    changeStateColour('alt_msgs', 'red');
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
    timeoutFunc = setTimeout(showNoResponseMessage, timeOutPeriod);
});
