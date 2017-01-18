// The client control code is more extensive so as to reduce the total number of requests going
//  to the server, so as to reduce latency issues over 3G

// Create a namespace if not existing
var tricap = tricap || {};

// Code here will be linted with JSHint. Doesn't understand Jinja2.
/* jshint ignore:start */
var numCams = {{num_cams}};
var imgTooOldCount = {{python_data.img_too_old_count}};
var camRefreshRate = {{python_data.refresh_rate}};
var stateRefreshRate = {{python_data.refresh_rate}};
var timeOutPeriod = {{python_data.timeout_period}};
var altiTarget = {{python_data.alti_target}};
var altiRange = {{python_data.alti_range}};
var vibrate = "{{python_data.vibrate}}";;
// Code here will be ignored by JSHint.
/* jshint ignore:end */

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

//This should change as you change the CSS file
tricap.RED_CLASS = 'danger';
tricap.ORANGE_CLASS = 'warning';
tricap.GREEN_CLASS = 'success';
tricap.BLUE_CLASS = 'info';
tricap.GREY_CLASS = 'tricap-grey';

//Object Constructors

function camImgController() {
    this.imgId = 0;
    this.lastRequestId = -1;
    this.oldImgCount = 0;
}

function timer(timedFunc, delay) {
    // Uses the setInterval and clearInterval to manage timing a function
    this._timedFunc = timedFunc;
    this.running = false;
    this.delay = delay;

    this._timer = undefined;

    this.runTimer = function(){
        if (this.running === false){
            this._timer = setInterval(this._timedFunc, this.delay);
            this.running = true;
        }
    };

    this.stopTimer = function(){
        if (this.running === true){
            clearInterval(this._timer);
            this.running = false;
        }
    };
}

//Globals

var camImgControllers = [];
var timeoutFunc;
var camRefreshTimer;
var oldTalkBoxMsgs = [];

// Then function declarations (i.e. function addTwoNumbers(a, b){ return a+b;};) so that hoisting
// is obvious

function _get_element_pre(elem_id){
    //Check if its an alert (i.e. a div) or a button (i.e. an a)


    var pre;
    if ($('#'+elem_id).is('div') === true){
        pre='alert-';
    } else if ($('#'+elem_id).is('a') === true){
        pre='btn-';
    }

    return pre;
}

function changeStateColour(elem_id, target_colour){

    var elem = $('#'+elem_id);
    var pre = _get_element_pre(elem_id);

    // remove state colour
    elem.removeClass(pre+tricap.GREEN_CLASS+' '+pre+tricap.ORANGE_CLASS+' '+pre+tricap.RED_CLASS);

    // add correct colour
    if (target_colour === 'red'){
        elem.addClass(pre+tricap.RED_CLASS);
    } else if (target_colour === 'green'){
        elem.addClass(pre+tricap.GREEN_CLASS);
    } else if (target_colour === 'orange'){
        elem.addClass(pre+tricap.ORANGE_CLASS);
    }
}

function changeTimeColour(elem_id, target_colour){

    var elem = $('#'+elem_id);
    var pre = _get_element_pre(elem_id);

    // remove state colour
    elem.removeClass(pre+tricap.BLUE_CLASS+' '+pre+tricap.RED_CLASS+' '+pre+tricap.GREY_CLASS);

    if (target_colour === 'grey'){
        elem.addClass(pre+tricap.GREY_CLASS);
    } else if (target_colour === 'blue'){
        elem.addClass(pre+tricap.BLUE_CLASS);
    } else if (target_colour === 'red'){
        elem.addClass(pre+tricap.RED_CLASS);
    }
}

function showMainError(msg){
    $('#h_main_status').html(msg);
    changeStateColour('alt_main_status', 'red');
    changeStateColour('alt_msgs', 'red');
}

function changeMainStatus(colour, msg) {
    $('#h_main_status').html(msg);
    changeStateColour('alt_main_status', colour);
    changeStateColour('alt_msgs', colour);
}

// Then function expressions (i.e. var a = function(a,b){return a+b;};). Note that the var a is
// hoisted as var a = undefined. So watch out.

var buttonClick = function(buttonCode){

    if (buttonCode === tricap.BUTTON_CODES.START || buttonCode === tricap.BUTTON_CODES.STOP ||
        buttonCode === tricap.BUTTON_CODES.STARTSTOP){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode }, startStopFollowUp);
    } else if (buttonCode === tricap.BUTTON_CODES.RESET){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode },
                  function(){location.reload(); return false;});
    } else if (buttonCode === tricap.BUTTON_CODES.TEST){
        // TODO When we think of other tests to do on the server side, send a test code through
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: tricap.BUTTON_CODES.START},
                  startStopFollowUp);
        setTimeout(function(){
            $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: tricap.BUTTON_CODES.STOP},
                      startStopFollowUp);
        }, stateRefreshRate*3);
    }
    return false;
};

var startStopFollowUp = function (data) {
    if (data.capture_started === true){
        camRefreshTimer.runTimer();
        // $('#btn_startstop').html('Stop');
        $('[name="btn_startstop"]').html('Stop');
    } else {
        camRefreshTimer.stopTimer();
        // $('#btn_startstop').html('Start');
        $('[name="btn_startstop"]').html('Start');
    }
    return false;
};

var refreshCamImages = function(){
    for (index = 0; index < camImgControllers.length; index++){
        if (camImgControllers[index].imgId !== camImgControllers[index].lastRequestId){
            var cam_img_url = $SCRIPT_ROOT + '/cam_img'+index+camImgControllers[index].imgId;
            $('#img_cam'+index).attr('src', cam_img_url);
            changeTimeColour('alt_cam'+index, 'blue');
            camImgControllers[index].lastRequestId = camImgControllers[index].imgId;
            camImgControllers[index].oldImgCount = 0;
        } else {
            camImgControllers[index].oldImgCount = camImgControllers[index].oldImgCount + 1;
            if (camImgControllers[index].oldImgCount < imgTooOldCount){
                changeTimeColour('alt_cam'+index, 'grey');
            } else {
                changeTimeColour('alt_cam'+index, 'red');
            }
        }
    }
    return false;
};

var updateAlti = function(data){
    $('#h_alti').html('Altitude: ' + data.measurement + ' m');

    changeStateColour('alt_alti', data.state_colour);
    changeStateColour('alt_alti_inner', data.state_colour);
    changeStateColour('btn_alti', data.state_colour);

    if (data.state_colour === 'red'){
        changeMainStatus('red', 'Altimeter Error');
    }

    if (data.measurement < altiTarget-altiRange){
        changeTimeColour('alt_alti_target', 'red');
        $('#h_alti_target').html('Below target range');
    } else if (data.measurement > altiTarget+altiRange) {
        changeTimeColour('alt_alti_target', 'red');
        $('#h_alti_target').html('Above target range');
    } else {
        changeTimeColour('alt_alti_target', 'blue');
        $('#h_alti_target').html('Within target range');
    }

    return false;
};


var updateCamState = function(data){
    changeStateColour('alt_cam_overall', data.overall_cam_state_colour);
    changeStateColour('btn_cam', data.overall_cam_state_colour);

    for (index = 0; index < camImgControllers.length; index++){
        camImgControllers[index].imgId = data.image_counts[index];
    }

    if (data.overall_cam_state_colour === 'red'){
        changeMainStatus('red', 'Camera Error');
    }

    startStopFollowUp(data);

    return false;
};

var updateTalkBox = function(data){

    // Clear the talkbox of all old messages
    $('[target=tb_msg]').remove();

    var newTalkBoxMsgs = [];
    var newMsgs = false;
    var index = 0;

    for (index = 0; index < data.msgs.length; index++){
        newTalkBoxMsgs.push(data.msgs[index]+data.reply_codes[index]);
    }

    if (oldTalkBoxMsgs.length !== newTalkBoxMsgs.length) {
        newMsgs = true;
    } else {
        for (index = 0; index < data.msgs.length; index++) {
            if (oldTalkBoxMsgs[index] !== newTalkBoxMsgs[index]){
                newMsgs = true;
            }
        }
    }

    if (newMsgs === true) {
        if (vibrate === 'yes') {
            navigator.vibrate = navigator.vibrate || navigator.webkitVibrate || navigator.mozVibrate || navigator.msVibrate;
            navigator.vibrate([300, 50, 300, 50, 300]);
        }
    }
    oldTalkBoxMsgs = newTalkBoxMsgs;

    for (index = data.msgs.length-1; index >= 0; index--){
        var reply_code = data.reply_codes[index];
        var yes_class = 'btn-default';
        var no_class = 'btn-default';
        if (reply_code === 1){
            yes_class = 'btn-success';
        } else if (reply_code === 2){
            no_class = 'btn-success';
        }

        $('#alt_msgs_talkbox').append(
            // '<input type="text" class="form-control" disabled="" target="tb_msg" value="'+data.msgs[index]+'">'
            '<div class="input-group" target="tb_msg">' +
                '<input type="text" class="form-control" disabled="" value="'+data.msgs[index]+'">'+
                '<span class="input-group-btn">'+
                    '<button type="button" class="btn '+yes_class+'" target="tb_msg_btn">Yes</a>' +
                    '<button type="button" class="btn '+no_class+'" target="tb_msg_btn">No</a>' +
                '</span></div>'
        );
    }

    $('[target=tb_msg_btn]').click(function(){
        // Need to change both buttons to default colouring, then change the active buttons colour
        // There is probably a better way to do this
        $(this).parent().children().removeClass('btn-success');
        $(this).parent().children().addClass('btn-default');
        $(this).removeClass('btn-default');
        $(this).addClass('btn-success');

        var msg = $(this).parent().parent().find('input').val();
        var reply_code;
        if ($(this).html() === 'Yes'){
            reply_code = 1;
        } else {
            reply_code = 2;
        }
        $.getJSON($SCRIPT_ROOT + '/_change_message_reply', {msg: msg, reply_code: reply_code});
    });
};

var updateSysMsgs = function(data){
    // Clear the errorbox of all old messages
    $('[target=sys_msg]').remove();

    if (data.msgs.length === 0) {
        $('#alt_msgs_sys').append(
            '<input type="text" class="form-control" disabled="" target="sys_msg" value="'+
            'No errors to report" id="input_sys_msg0">'
        );
    }

    for (var index = data.msgs.length-1; index >= 0; index--){
        $('#alt_msgs_sys').append(
            '<input type="text" class="form-control" disabled="" target="sys_msg" value="'+
            data.msgs[index]+' id=input_sys_msg'+index+'">'
        );
    }};

var updatePage = function(data){
    //Reset the timeout period
    clearTimeout(timeoutFunc);
    timeoutFunc = setTimeout(function(){
                      changeMainStatus('red', 'No Response From Server');},
                      timeOutPeriod);
     //Check if we had recovered from a timeout
     if ($('#h_main_status').html() === 'No Response From Server') {
         changeMainStatus('green', 'TriCap');
     }

     updateAlti(data.alti);
     updateCamState(data.cams);
     updateTalkBox(data.talk);
     updateSysMsgs(data.sys);

     return false;
};

var requestStateData = function(data){
    $.getJSON($SCRIPT_ROOT + '/_get_state_data', {}, updatePage);
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
    // $("#btn_startstop").on('click', function(event){buttonClick(tricap.BUTTON_CODES.STARTSTOP);});
    $('[name="btn_startstop"]').on('click', function(event){buttonClick(tricap.BUTTON_CODES.STARTSTOP);});
    $('#a_test').attr('href', '#');
    $("#a_test").click(function(event){buttonClick(tricap.BUTTON_CODES.TEST); return true;});
    $("#img_cam_left").error(function(event){console.log('Error');});

    $("#input_talkbox").keyup(function(event){
        if (event.keyCode == 13){
            // updateOldTalkBoxMsgs();
            $.getJSON($SCRIPT_ROOT + '/_submit_talkbox_msg', {msg:$(this).val()});
            $(this).val('');
        }
    });
    //replace the link for settings, making it stop any recording before going to the settings page
    $('#a_settings').removeProp('onclick');
    $('#a_settings').click(function(e){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: tricap.BUTTON_CODES.STOP},
                  function(data){
                      $(location).attr('href', "{{url_for('settings.settings')}}");
                  });
        return false;
    });

    //replace the link for settings
    $('#a_showlog').removeProp('onclick');
    $('#a_showlog').click(function(e){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: tricap.BUTTON_CODES.STOP},
                  function(data){
                      $(location).attr('href', "{{url_for('showlog.showlog')}}");
                  });
        return false;
    });

    // Set the interval functions
    camRefreshTimer = new timer(refreshCamImages, camRefreshRate);
    setInterval(requestStateData, stateRefreshRate);
    timeoutFunc = setTimeout(function(){showMainError('No Response From Server');}, timeOutPeriod);
});


// function updateOldTalkBoxMsgs(){
//     oldTalkBoxMsgs = [];
//     oldTalkBoxMsgs.push($("#input_talkbox").val()+'3');
//     var tbDiv = $("#alt_msgs_talkbox").find('div').first()
//     for (var i = 0; i < $("#alt_msgs_talkbox").find('div').length; i++) {
//         if (i < $("#alt_msgs_talkbox").find('div').length-1) {
//             var msg = tbDiv.find('input').val();
//             var btn = tbDiv.find('button').first();
//             var reply_code = '3';
//             if (btn.hasClass('btn-success')) {
//                 reply_code = '1';
//             } else if (btn.next().hasClass('btn-success')) {
//                 reply_code = '2';
//             }
//             oldTalkBoxMsgs.push(msg+reply_code);
//         }
//         tbDiv = tbDiv.next()
//     }
//     oldTalkBoxMsgs.reverse();
//     console.log(oldTalkBoxMsgs);
// }
