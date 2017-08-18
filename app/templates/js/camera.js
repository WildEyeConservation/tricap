// Code needed to give the camera template extra functionality
// All of the following code will only run when the page is ready
//  (the $() is short for $(document).ready())

var batteryWarning = 50
var spaceWarning = 145000
//var battery0 = parseInt({{battery[0]}})

$(function(){
    // Check for low battery
    if({{battery[0]}} < batteryWarning){
        $('#middle_camera').removeClass('alert-info');
        $('#middle_camera').addClass('alert-danger');
    } else {
        $('#middle_camera').removeClass('alert-danger');
        $('#middle_camera').addClass('alert-info');
    }

    if({{battery[1]}} < batteryWarning){
        $('#front_camera').removeClass('alert-info');
        $('#front_camera').addClass('alert-danger');
    } else {
        $('#front_camera').removeClass('alert-danger');
        $('#front_camera').addClass('alert-info');
    }

    if({{battery[2]}} < batteryWarning){
        $('#back_camera').removeClass('alert-info');
        $('#back_camera').addClass('alert-danger');
    } else {
        $('#back_camera').removeClass('alert-danger');
        $('#back_camera').addClass('alert-info');
    }

        if({{free_space[0]}} < spaceWarning){
        $('#middle_camera').removeClass('alert-info');
        $('#middle_camera').addClass('alert-danger');
    } else {
        $('#middle_camera').removeClass('alert-danger');
        $('#middle_camera').addClass('alert-info');
    }

    if({{free_space[1]}} < spaceWarning){
        $('#front_camera').removeClass('alert-info');
        $('#front_camera').addClass('alert-danger');
    } else {
        $('#front_camera').removeClass('alert-danger');
        $('#front_camera').addClass('alert-info');
    }

    if({{free_space[2]}} < spaceWarning){
        $('#back_camera').removeClass('alert-info');
        $('#back_camera').addClass('alert-danger');
    } else {
        $('#back_camera').removeClass('alert-danger');
        $('#back_camera').addClass('alert-info');
    }
});